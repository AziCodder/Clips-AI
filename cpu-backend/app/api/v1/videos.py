from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Approval, ApprovalStatus, Highlight, TranscriptionJob, User, Video, VideoStatus
from app.schemas.video import VideoDetailRead, VideoListResponse, VideoManualCreate, VideoRead
from app.services import s3_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


def _to_read(v: Video) -> VideoRead:
    return VideoRead(
        id=v.id,
        topic_id=v.topic_id,
        source=v.source,
        source_id=v.source_id,
        url=v.url,
        title=v.title,
        channel=v.channel,
        views=v.views,
        duration_sec=v.duration_sec,
        status=v.status,
        thumbnail_url=v.thumbnail_url,
        created_at=v.created_at,
    )


def _to_detail(v: Video) -> VideoDetailRead:
    return VideoDetailRead(
        id=v.id,
        topic_id=v.topic_id,
        source=v.source,
        source_id=v.source_id,
        url=v.url,
        title=v.title,
        channel=v.channel,
        views=v.views,
        duration_sec=v.duration_sec,
        status=v.status,
        thumbnail_url=v.thumbnail_url,
        created_at=v.created_at,
        description=v.description,
        likes=v.likes,
        publish_date=v.publish_date,
    )


@router.get("", response_model=VideoListResponse)
async def list_videos(
    topic_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Video)
    if topic_id:
        stmt = stmt.where(Video.topic_id == topic_id)
    if status:
        stmt = stmt.where(Video.status == status)
    if q:
        safe_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Video.title.ilike(f"%{safe_q}%", escape="\\"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Video.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    videos = (await db.execute(stmt)).scalars().all()

    return VideoListResponse(
        items=[_to_read(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/manual", response_model=VideoRead)
async def add_manual_video(
    body: VideoManualCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add a video URL for processing. Supports YouTube, VK and other yt-dlp sources."""
    from app.services.ytdlp_service import dry_run_check

    # Fast check: exact URL already in DB — no yt-dlp needed
    existing_by_url = (
        await db.execute(select(Video).where(Video.url == body.url))
    ).scalar_one_or_none()
    if existing_by_url:
        response.status_code = status.HTTP_200_OK
        return _to_read(existing_by_url).model_copy(update={"already_exists": True})

    try:
        info = dry_run_check(body.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"URL недоступен для скачивания: {exc}")

    now = datetime.now(timezone.utc)
    video = Video(
        id=uuid.uuid4(),
        topic_id=body.topic_id,
        source=info["source"],
        source_id=info["source_id"],
        url=body.url,
        title=info["title"],
        description=info["description"],
        channel=info["channel"],
        views=info["views"],
        likes=info["likes"],
        duration_sec=info["duration_sec"],
        thumbnail_url=info["thumbnail_url"],
        status=VideoStatus.PENDING_APPROVAL,
        created_at=now,
        updated_at=now,
    )
    db.add(video)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(Video).where(Video.source == info["source"], Video.source_id == info["source_id"])
            )
        ).scalar_one_or_none()
        response.status_code = status.HTTP_200_OK
        return _to_read(existing).model_copy(update={"already_exists": True})

    approval_status = ApprovalStatus.APPROVED if body.auto_approve else ApprovalStatus.PENDING
    video.status = VideoStatus.APPROVED if body.auto_approve else VideoStatus.PENDING_APPROVAL

    approval = Approval(
        video_id=video.id,
        status=approval_status,
        created_at=now,
    )
    db.add(approval)
    await db.commit()
    await db.refresh(video)
    response.status_code = status.HTTP_201_CREATED

    # Send to Telegram for approval (unless auto_approve)
    if not body.auto_approve and current_user.telegram_id:
        from app.services.telegram_service import send_video_candidate
        import asyncio
        asyncio.create_task(send_video_candidate(
            chat_id=current_user.telegram_id,
            approval_id=approval.id,
            title=video.title,
            url=video.url,
            topic_name="Manual",
            thumbnail_url=video.thumbnail_url,
            duration_sec=video.duration_sec,
            views=video.views,
        ))

    # Auto-approve: immediately start download → GPU pipeline
    if body.auto_approve:
        try:
            import app.tasks.celery_app  # noqa: F401
            from app.tasks.pipeline_tasks import task_download_approved
            task_download_approved.apply_async(queue="pipeline")
            log.info("task_download_approved triggered for auto-approved video %s", video.id)
        except Exception as exc:
            log.warning("Could not trigger task_download_approved: %s", exc)

    return _to_read(video)


@router.get("/{video_id}", response_model=VideoDetailRead)
async def get_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return _to_detail(video)


@router.post("/{video_id}/refresh-metadata", status_code=status.HTTP_200_OK)
async def refresh_video_metadata(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Re-fetch metadata (duration, views, title, etc.) from the video URL and update the record."""
    from app.services.ytdlp_service import dry_run_check

    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        info = dry_run_check(video.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not fetch metadata: {exc}") from exc

    video.title = info.get("title") or video.title
    video.description = info.get("description") or video.description
    video.channel = info.get("channel") or video.channel
    video.views = info.get("views", 0) or 0
    video.likes = info.get("likes", 0) or 0
    video.duration_sec = info.get("duration_sec", 0) or 0
    video.thumbnail_url = info.get("thumbnail_url") or video.thumbnail_url
    await db.commit()
    await db.refresh(video)
    return _to_detail(video)


@router.post("/{video_id}/request-analysis", status_code=status.HTTP_202_ACCEPTED)
async def request_analysis(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Queue LLM analysis for a transcribed video."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status not in (VideoStatus.TRANSCRIBED, VideoStatus.ANALYZED):
        raise HTTPException(status_code=400, detail=f"Video status '{video.status}' is not ready for analysis")
    video.status = VideoStatus.TRANSCRIBED
    await db.commit()
    from app.tasks.pipeline_tasks import task_run_llm_analysis
    task_run_llm_analysis.delay()
    return {"detail": "Analysis queued"}


@router.post("/{video_id}/recompute-highlights", status_code=status.HTTP_202_ACCEPTED)
async def recompute_highlights(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Delete existing highlights and re-run LLM analysis."""
    from sqlalchemy import delete
    from app.db.models import Highlight

    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    await db.execute(delete(Highlight).where(Highlight.video_id == video_id))
    video.status = VideoStatus.TRANSCRIBED
    await db.commit()
    from app.tasks.pipeline_tasks import task_run_llm_analysis
    task_run_llm_analysis.delay()
    return {"detail": "Highlights recompute queued"}


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: uuid.UUID,
    scope: Literal["all", "video_only"] = Query(
        default="all",
        description="all = удалить видео и всё связанное (нарезки, тексты, ассеты). video_only = удалить только текст/описание/транскрипт, нарезки остаются.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if scope == "all":
        try:
            s3_service.delete_prefix(f"videos/{video_id}/")
        except Exception as e:  # noqa: BLE001
            log.warning("S3 delete_prefix failed for video_id=%s, continuing with DB delete: %s", video_id, e)
        await db.execute(delete(Approval).where(Approval.video_id == video_id))
        await db.delete(video)
        await db.commit()
        return

    if scope == "video_only":
        jobs_result = await db.execute(
            select(TranscriptionJob).where(TranscriptionJob.video_id == video_id)
        )
        jobs = jobs_result.scalars().all()
        for job in jobs:
            try:
                s3_service.delete_prefix(f"videos/{video_id}/transcripts/{job.id}/")
            except Exception:
                log.warning("S3 delete_prefix failed for transcript job_id=%s, continuing", job.id, exc_info=True)
        await db.execute(delete(TranscriptionJob).where(TranscriptionJob.video_id == video_id))
        video.description = ""
        await db.commit()
        await db.refresh(video)
        return
