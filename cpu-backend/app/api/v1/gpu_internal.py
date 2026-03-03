from __future__ import annotations

import logging
import uuid

log = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_gpu_api_key
from app.core.config import settings
from app.db.models import Asset, AssetType, JobStatus, TranscriptionJob, User, Video, VideoStatus
from app.schemas.gpu import (
    GpuJobAckResponse,
    GpuJobCompletedRequest,
    GpuJobFailedRequest,
    GpuJobNextResponse,
    GpuJobStartedRequest,
)
from app.services import s3_service

router = APIRouter(
    prefix="/gpu",
    tags=["gpu-internal"],
    dependencies=[Depends(verify_gpu_api_key)],
)


@router.get("/jobs/next", response_model=GpuJobNextResponse | None)
async def get_next_job(db: AsyncSession = Depends(get_db)):
    """
    GPU worker polls this to get the next queued job.
    Jobs are selected by priority DESC, created_at ASC.
    """
    result = await db.execute(
        select(TranscriptionJob)
        .where(TranscriptionJob.status == JobStatus.QUEUED)
        .order_by(TranscriptionJob.priority.desc(), TranscriptionJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    # Lease the job
    job.status = JobStatus.LEASED
    job.lease_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JOB_LEASE_TTL_HOURS)
    await db.commit()

    return GpuJobNextResponse(
        job_id=job.id,
        video_id=job.video_id,
        s3_audio_key=job.s3_audio_key,
        batch_size=8,
        compute_type="float16",
        results_prefix=f"videos/{job.video_id}/transcripts/{job.id}/",
    )


@router.post("/jobs/{job_id}/started", status_code=status.HTTP_204_NO_CONTENT)
async def mark_started(
    job_id: uuid.UUID,
    body: GpuJobStartedRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = JobStatus.STARTED
    job.lease_owner = body.worker_id
    job.started_at = body.started_at
    await db.commit()


@router.post("/jobs/{job_id}/completed", response_model=GpuJobAckResponse)
async def mark_completed(
    job_id: uuid.UUID,
    body: GpuJobCompletedRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify S3 bundle
    missing = s3_service.verify_transcript_bundle(str(job.video_id), str(job.id))
    if missing:
        job.status = JobStatus.FAILED
        job.error = f"Missing S3 files: {missing}"
        await db.commit()
        return GpuJobAckResponse(ack=False, reason=f"Missing files: {missing}")

    job.status = JobStatus.ACKNOWLEDGED
    job.s3_results_prefix = body.s3_prefix_results
    job.finished_at = datetime.now(timezone.utc)

    # Update video status
    video_result = await db.execute(select(Video).where(Video.id == job.video_id))
    video = video_result.scalar_one_or_none()
    if video:
        video.status = VideoStatus.TRANSCRIBED

    # Save transcript assets
    # (LLM analysis will be triggered after commit below)
    prefix = f"videos/{job.video_id}/transcripts/{job.id}"
    asset_map = {
        AssetType.TRANSCRIPT_TXT: f"{prefix}/transcript.txt",
        AssetType.TRANSCRIPT_WORDS: f"{prefix}/words.json",
        AssetType.TRANSCRIPT_SEGMENTS: f"{prefix}/segments.json",
        AssetType.SUBTITLE_SRT: f"{prefix}/subtitles.srt",
    }
    for atype, s3_key in asset_map.items():
        db.add(Asset(video_id=job.video_id, type=atype, s3_key=s3_key))

    await db.commit()

    # Immediately start LLM analysis for this transcribed video
    try:
        import app.tasks.celery_app  # ensure Celery app + routes are loaded  # noqa: F401
        from app.tasks.pipeline_tasks import task_run_llm_analysis
        task_run_llm_analysis.apply_async(queue="pipeline")
    except Exception as exc:
        log.warning("Could not trigger task_run_llm_analysis: %s", exc)

    return GpuJobAckResponse(ack=True, reason="")


@router.post("/jobs/{job_id}/failed", status_code=status.HTTP_204_NO_CONTENT)
async def mark_failed(
    job_id: uuid.UUID,
    body: GpuJobFailedRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.attempts += 1
    tb = body.traceback
    truncated_tb = (tb[:500] + " ... [truncated]") if len(tb) > 500 else tb
    job.error = f"{body.error_type}: {truncated_tb}"
    job.status = JobStatus.QUEUED if (body.retryable and job.attempts < settings.JOB_MAX_ATTEMPTS) else JobStatus.FAILED
    job.lease_owner = None
    job.lease_expires_at = None
    await db.commit()


@router.get("/jobs/{job_id}/ack", response_model=GpuJobAckResponse)
async def check_ack(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return GpuJobAckResponse(ack=False, reason="Job not found")
    return GpuJobAckResponse(ack=job.status == JobStatus.ACKNOWLEDGED, reason=job.status)


@router.post("/jobs/{job_id}/cleanup-done", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_done(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if job:
        job.status = JobStatus.CLEANUP_DONE
        await db.commit()


@router.post("/jobs/{job_id}/timeout", status_code=status.HTTP_204_NO_CONTENT)
async def mark_job_timeout(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Called by GPU worker when a job exceeds JOB_MAX_DURATION_SEC.
    Marks job as timed_out and notifies admin via Telegram.
    """
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = JobStatus.TIMED_OUT
    job.error = "Job exceeded maximum allowed duration (2 hours)"
    job.lease_owner = None
    job.lease_expires_at = None
    await db.commit()

    # Notify admin via Telegram
    try:
        admin_result = await db.execute(
            select(User)
            .where(User.telegram_id.isnot(None), User.is_active.is_(True))
            .limit(1)
        )
        admin = admin_result.scalar_one_or_none()
        if admin and admin.telegram_id:
            video_result = await db.execute(select(Video).where(Video.id == job.video_id))
            video = video_result.scalar_one_or_none()
            title = video.title if video else str(job.video_id)

            from app.services.telegram_service import send_timeout_notification
            await send_timeout_notification(
                chat_id=admin.telegram_id,
                video_title=title,
                job_id=str(job_id),
            )
    except Exception as exc:
        log.warning("Could not send timeout TG notification for job %s: %s", job_id, exc)
