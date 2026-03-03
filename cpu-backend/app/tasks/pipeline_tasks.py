from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

from celery import shared_task

from app.core.config import settings

log = logging.getLogger(__name__)


# ── Stage 1: Search Candidates (08:00 MSK) ────────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_search_candidates", bind=True, max_retries=2)
def task_search_candidates(self):
    """Search YouTube for video candidates per topic and send to Telegram for approval."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import Topic, Video, Approval, VideoStatus, ApprovalStatus
    from app.services.video_search_service import search_youtube_api, search_ytdlp_fallback, run_dry_run

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        topics = db.query(Topic).filter(Topic.enabled == True).all()
        total_duration = 0
        max_duration = settings.SEARCH_MAX_TOTAL_DURATION_MIN * 60

        for topic in topics:
            keywords = json.loads(topic.keywords_json or "[]")
            if not keywords:
                continue

            candidates_found = 0
            for query in keywords:
                if candidates_found >= settings.SEARCH_MAX_VIDEOS_PER_TOPIC:
                    break
                if total_duration >= max_duration:
                    log.info("Daily duration limit reached, stopping search")
                    break

                try:
                    results = asyncio.run(search_youtube_api(query, max_results=10))
                    if not results:
                        results = asyncio.run(search_ytdlp_fallback(query, max_results=5))
                except Exception as exc:
                    log.warning("Search failed for '%s': %s", query, exc)
                    continue

                for candidate in results:
                    if candidates_found >= settings.SEARCH_MAX_VIDEOS_PER_TOPIC:
                        break
                    if total_duration + candidate["duration_sec"] > max_duration:
                        continue

                    # Skip already known videos
                    existing = db.query(Video).filter(
                        Video.source == candidate["source"],
                        Video.source_id == candidate["source_id"],
                    ).first()
                    if existing:
                        continue

                    # Dry-run check
                    try:
                        asyncio.run(run_dry_run(candidate["url"]))
                    except Exception as exc:
                        log.info("Dry-run failed for %s: %s", candidate["url"], exc)
                        continue

                    # Create video + approval
                    video = Video(
                        id=uuid.uuid4(),
                        topic_id=topic.id,
                        source=candidate["source"],
                        source_id=candidate["source_id"],
                        url=candidate["url"],
                        title=candidate["title"],
                        description=candidate["description"],
                        channel=candidate["channel"],
                        views=candidate["views"],
                        likes=candidate["likes"],
                        duration_sec=candidate["duration_sec"],
                        thumbnail_url=candidate["thumbnail_url"],
                        status=VideoStatus.PENDING_APPROVAL,
                    )
                    db.add(video)
                    db.flush()

                    approval = Approval(
                        video_id=video.id,
                        status=ApprovalStatus.PENDING,
                    )
                    db.add(approval)
                    db.flush()

                    # Send to Telegram (find first admin user with telegram_id)
                    from app.db.models import User
                    admin = db.query(User).filter(User.telegram_id != None, User.is_active == True).first()
                    if admin and admin.telegram_id:
                        asyncio.run(_send_candidate_tg(
                            chat_id=admin.telegram_id,
                            approval_id=approval.id,
                            title=video.title,
                            url=video.url,
                            topic_name=topic.name,
                            thumbnail_url=video.thumbnail_url,
                            duration_sec=video.duration_sec,
                            views=video.views,
                        ))
                        approval.tg_chat_id = admin.telegram_id

                    total_duration += candidate["duration_sec"]
                    candidates_found += 1

            db.commit()
    log.info("task_search_candidates done")


async def _send_candidate_tg(**kwargs):
    from app.services.telegram_service import send_video_candidate
    await send_video_candidate(**kwargs)


# ── Stage 2: Download Approved (11:00 MSK) ────────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_download_approved", bind=True)
def task_download_approved(self):
    """Download all approved videos, extract audio, upload to S3."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import Video, VideoStatus, Asset, AssetType
    from app.services.ytdlp_service import download_video
    from app.services.ffmpeg_service import extract_audio_flac
    from app.services import s3_service

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        videos = db.query(Video).filter(Video.status == VideoStatus.APPROVED).all()
        log.info("Downloading %d approved videos", len(videos))

        for video in videos:
            try:
                video.status = VideoStatus.DOWNLOADING
                db.commit()

                with tempfile.TemporaryDirectory() as tmpdir:
                    # Download
                    video_path = download_video(video.url, tmpdir)

                    # Upload master video
                    master_key = f"videos/{video.id}/master.mp4"
                    size = s3_service.upload_file(video_path, master_key, "video/mp4")
                    db.add(Asset(video_id=video.id, type=AssetType.MASTER_VIDEO, s3_key=master_key, size_bytes=size))

                    video.status = VideoStatus.DOWNLOADED
                    db.commit()

                    # Extract audio FLAC
                    audio_path = extract_audio_flac(video_path, tmpdir)
                    audio_key = f"videos/{video.id}/audio/audio.flac"
                    audio_size = s3_service.upload_file(audio_path, audio_key, "audio/flac")
                    db.add(Asset(video_id=video.id, type=AssetType.AUDIO, s3_key=audio_key, size_bytes=audio_size))

                    video.status = VideoStatus.AUDIO_READY
                    db.commit()

                    # Upload thumbnail if URL available
                    if video.thumbnail_url:
                        try:
                            import httpx
                            r = httpx.get(video.thumbnail_url, timeout=10)
                            thumb_key = f"videos/{video.id}/thumb.jpg"
                            import io
                            s3_service.upload_fileobj(io.BytesIO(r.content), thumb_key, "image/jpeg")
                            db.add(Asset(video_id=video.id, type=AssetType.THUMB, s3_key=thumb_key))
                        except Exception:
                            pass

                    db.commit()

            except Exception as exc:
                log.error("Failed to download video %s: %s", video.id, exc)
                video.status = VideoStatus.FAILED
                db.commit()

    log.info("task_download_approved done")
    # Immediately queue GPU jobs for newly downloaded videos
    task_start_gpu_pod.apply_async(queue="pipeline")


# ── Stage 3: Start GPU Pod + Queue jobs (14:00 MSK) ───────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_start_gpu_pod", bind=True)
def task_start_gpu_pod(self):
    """Queue transcription jobs for AUDIO_READY videos, then start GPU on demand."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import Video, VideoStatus, TranscriptionJob, JobStatus, Asset, AssetType

    engine = create_engine(settings.SYNC_DATABASE_URL)
    queued_any = False
    with Session(engine) as db:
        videos = db.query(Video).filter(Video.status == VideoStatus.AUDIO_READY).all()

        for video in videos:
            audio_asset = db.query(Asset).filter(
                Asset.video_id == video.id,
                Asset.type == AssetType.AUDIO,
            ).first()
            if not audio_asset:
                continue

            job = TranscriptionJob(
                id=uuid.uuid4(),
                video_id=video.id,
                status=JobStatus.QUEUED,
                s3_audio_key=audio_asset.s3_key,
                s3_results_prefix=f"videos/{video.id}/transcripts/",
            )
            db.add(job)
            video.status = VideoStatus.QUEUED_GPU
            db.commit()
            queued_any = True
            log.info("Queued transcription job %s for video %s", job.id, video.id)

    if queued_any:
        task_ensure_gpu_running.apply_async(queue="pipeline")

    log.info("task_start_gpu_pod done")


REDIS_GPU_INSTANCE_KEY = "clips:gpu_instance_id"
REDIS_GPU_INSTANCE_TTL = 86400  # 24h


def _get_redis():
    import redis
    return redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


@shared_task(name="app.tasks.pipeline_tasks.task_ensure_gpu_running", bind=True)
def task_ensure_gpu_running(self):
    """
    Start a Vast.ai GPU instance only if there are QUEUED transcription jobs
    and no instance is already running (idempotent: calling twice is safe).
    Stores instance_id in Redis to avoid starting duplicates.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import TranscriptionJob, JobStatus, User
    from app.services import vastai_service, telegram_service

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        queued_count = db.query(TranscriptionJob).filter(
            TranscriptionJob.status == JobStatus.QUEUED
        ).count()

        if queued_count == 0:
            log.info("task_ensure_gpu_running: no queued jobs, skipping GPU start")
            return

        # Check if we already have a running instance
        r = _get_redis()
        existing_id = r.get(REDIS_GPU_INSTANCE_KEY)
        if existing_id:
            try:
                status_str = asyncio.run(vastai_service.get_instance_status(int(existing_id)))
                if status_str in ("CONNECT", "OPEN"):
                    log.info("task_ensure_gpu_running: instance %s already running (%s), skipping", existing_id, status_str)
                    return
                log.info("task_ensure_gpu_running: instance %s status=%s, clearing and starting new", existing_id, status_str)
            except Exception as exc:
                log.warning("task_ensure_gpu_running: failed to check instance %s: %s", existing_id, exc)
            r.delete(REDIS_GPU_INSTANCE_KEY)

        log.info("task_ensure_gpu_running: %d queued jobs — starting Vast.ai instance", queued_count)
        instance_id = asyncio.run(vastai_service.start_instance())
        if instance_id is None:
            log.warning("task_ensure_gpu_running: failed to start Vast.ai instance")
            admin = db.query(User).filter(User.telegram_id != None, User.is_active == True).first()
            if admin and admin.telegram_id:
                asyncio.run(telegram_service.send_notification(
                    admin.telegram_id,
                    f"Vast.ai: не удалось запустить GPU инстанс. {queued_count} задач в очереди."
                ))
        else:
            r.set(REDIS_GPU_INSTANCE_KEY, str(instance_id), ex=REDIS_GPU_INSTANCE_TTL)
            log.info("task_ensure_gpu_running: started instance %s", instance_id)

    log.info("task_ensure_gpu_running done")


@shared_task(name="app.tasks.pipeline_tasks.task_destroy_idle_gpu", bind=True)
def task_destroy_idle_gpu(self):
    """
    Destroy Vast.ai GPU instance when there are no QUEUED or LEASED jobs.
    GPU worker exits after IDLE_SHUTDOWN_SEC (60s) with no jobs; this task
    runs every 2 min and destroys the instance to stop billing.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import TranscriptionJob, JobStatus
    from app.services import vastai_service

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        active_count = db.query(TranscriptionJob).filter(
            TranscriptionJob.status.in_((JobStatus.QUEUED, JobStatus.LEASED, JobStatus.STARTED))
        ).count()

    if active_count > 0:
        log.debug("task_destroy_idle_gpu: %d active jobs, skipping destroy", active_count)
        return

    r = _get_redis()
    instance_id_str = r.get(REDIS_GPU_INSTANCE_KEY)
    if not instance_id_str:
        return

    try:
        instance_id = int(instance_id_str)
        ok = asyncio.run(vastai_service.destroy_instance(instance_id))
        if ok:
            r.delete(REDIS_GPU_INSTANCE_KEY)
            log.info("task_destroy_idle_gpu: destroyed instance %s (no more jobs)", instance_id)
        else:
            log.warning("task_destroy_idle_gpu: failed to destroy instance %s", instance_id)
    except Exception as exc:
        log.warning("task_destroy_idle_gpu: error destroying %s: %s", instance_id_str, exc)


# ── Stage 4: LLM Analysis (01:00 MSK) ────────────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_run_llm_analysis", bind=True)
def task_run_llm_analysis(self):
    """Run LLM highlights extraction for all transcribed videos."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import Video, VideoStatus, Topic, Highlight, Asset, AssetType
    from app.services.llm.provider import get_llm_provider
    from app.services import s3_service

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        videos = db.query(Video).filter(Video.status == VideoStatus.TRANSCRIBED).all()
        provider = get_llm_provider()

        for video in videos:
            try:
                video.status = VideoStatus.ANALYZING
                db.commit()

                # Load transcript text from S3
                txt_asset = db.query(Asset).filter(
                    Asset.video_id == video.id,
                    Asset.type == AssetType.TRANSCRIPT_TXT,
                ).first()
                if not txt_asset:
                    log.warning("No transcript asset for video %s", video.id)
                    video.status = VideoStatus.FAILED
                    db.commit()
                    continue

                transcript_text = s3_service.download_fileobj(txt_asset.s3_key).decode("utf-8")

                topic = db.query(Topic).filter(Topic.id == video.topic_id).first()
                prompt = topic.prompt_for_highlights if topic else ""
                clips_count = topic.clips_per_video if topic else 3

                highlights = asyncio.run(provider.extract_highlights(transcript_text, prompt, clips_count))

                for h in highlights:
                    if h.end_sec <= h.start_sec:
                        continue
                    db.add(Highlight(
                        id=uuid.uuid4(),
                        video_id=video.id,
                        start_sec=h.start_sec,
                        end_sec=h.end_sec,
                        score=h.score,
                        title=h.title,
                        reason=h.reason,
                        prompt_used=prompt,
                    ))

                video.status = VideoStatus.ANALYZED
                db.commit()
                log.info("LLM analysis done for video %s: %d highlights", video.id, len(highlights))

            except Exception as exc:
                log.error("LLM analysis failed for video %s: %s", video.id, exc)
                video.status = VideoStatus.FAILED
                db.commit()

    log.info("task_run_llm_analysis done")
    # Immediately start clip rendering for analyzed videos
    task_render_clips_batch.apply_async(queue="clips")


# ── Stage 5: Render Clips (04:00 MSK) ────────────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_render_clips_batch", bind=True)
def task_render_clips_batch(self):
    """Render ffmpeg clips for all analyzed videos."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import Video, VideoStatus, Highlight, ClipJob, ClipJobStatus, Asset, AssetType
    from app.services import s3_service
    from app.services.ffmpeg_service import cut_clip
    import concurrent.futures
    import psutil

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        videos = db.query(Video).filter(Video.status == VideoStatus.ANALYZED).all()

        for video in videos:
            video.status = VideoStatus.CLIPS_RENDERING
            db.commit()

            video_asset = db.query(Asset).filter(
                Asset.video_id == video.id,
                Asset.type == AssetType.MASTER_VIDEO,
            ).first()
            if not video_asset:
                video.status = VideoStatus.FAILED
                db.commit()
                continue

            highlights = db.query(Highlight).filter(Highlight.video_id == video.id).all()

            # Idempotency: skip highlights that already have a non-FAILED ClipJob
            existing_clip_highlight_ids = {
                row.highlight_id
                for row in db.query(ClipJob.highlight_id).filter(
                    ClipJob.highlight_id.in_([h.id for h in highlights]),
                    ClipJob.status != ClipJobStatus.FAILED,
                ).all()
            }
            pending_highlights = [h for h in highlights if h.id not in existing_clip_highlight_ids]

            if not pending_highlights:
                log.info("All clips already rendered for video %s, skipping", video.id)
                video.status = VideoStatus.CLIPS_READY
                db.commit()
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                # Download master video
                local_video = os.path.join(tmpdir, "master.mp4")
                try:
                    s3_service.download_file(video_asset.s3_key, local_video)
                except Exception as exc:
                    log.error("Failed to download master video for %s: %s", video.id, exc)
                    video.status = VideoStatus.FAILED
                    db.commit()
                    continue

                semaphore = asyncio.Semaphore(settings.FFMPEG_MAX_CONCURRENT)

                def render_one(highlight: Highlight) -> tuple[str, str | None]:
                    clip_id = str(uuid.uuid4())
                    clip_path = os.path.join(tmpdir, f"{clip_id}.mp4")
                    s3_key = f"videos/{video.id}/clips/{clip_id}/clip.mp4"
                    try:
                        # Auto-pause on high CPU
                        while psutil.cpu_percent(interval=1) > 85:
                            import time; time.sleep(5)
                        cut_clip(local_video, highlight.start_sec, highlight.end_sec, clip_path)
                        s3_service.upload_file(clip_path, s3_key, "video/mp4")
                        return str(highlight.id), s3_key
                    except Exception as exc:
                        log.error("Clip render failed for highlight %s: %s", highlight.id, exc)
                        return str(highlight.id), None

                with concurrent.futures.ThreadPoolExecutor(max_workers=settings.FFMPEG_MAX_CONCURRENT) as pool:
                    futures = {pool.submit(render_one, h): h for h in pending_highlights}
                    for future in concurrent.futures.as_completed(futures):
                        highlight_id_str, s3_key = future.result()
                        hl = futures[future]
                        if s3_key:
                            db.add(ClipJob(
                                id=uuid.uuid4(),
                                highlight_id=hl.id,
                                status=ClipJobStatus.DONE,
                                s3_clip_key=s3_key,
                                finished_at=datetime.now(timezone.utc),
                            ))
                            db.add(Asset(
                                video_id=video.id,
                                type=AssetType.CLIP_VIDEO,
                                s3_key=s3_key,
                            ))
                        else:
                            db.add(ClipJob(
                                id=uuid.uuid4(),
                                highlight_id=hl.id,
                                status=ClipJobStatus.FAILED,
                            ))

            video.status = VideoStatus.CLIPS_READY
            db.commit()

    log.info("task_render_clips_batch done")


# ── Stage 6: Daily Notification (06:00 MSK) ───────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_send_daily_notification", bind=True)
def task_send_daily_notification(self):
    """Send Telegram notification: clips are ready."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.models import User, Video, VideoStatus
    from app.services.telegram_service import send_notification

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        admin = db.query(User).filter(User.telegram_id != None, User.is_active == True).first()
        if not admin or not admin.telegram_id:
            log.warning("No admin with telegram_id found")
            return

        ready_count = db.query(Video).filter(Video.status == VideoStatus.CLIPS_READY).count()
        text = f"Клипы готовы!\n\nВидео с готовыми клипами: {ready_count}\n\nПроверь сайт и подтверди."
        asyncio.run(send_notification(admin.telegram_id, text))

    log.info("task_send_daily_notification done")


# ── Reaper: check stale jobs (every 15 min) ───────────────────────────────────

@shared_task(name="app.tasks.pipeline_tasks.task_reaper", bind=True)
def task_reaper(self):
    """Return stale leased jobs to queued; notify on max attempts."""
    from sqlalchemy import create_engine, update as sa_update
    from sqlalchemy.orm import Session
    from app.db.models import TranscriptionJob, JobStatus, Video, User
    from app.services.telegram_service import send_failed_job_notification

    engine = create_engine(settings.SYNC_DATABASE_URL)
    now = datetime.now(timezone.utc)

    returned_to_queue = 0

    with Session(engine) as db:
        stale = db.query(TranscriptionJob).filter(
            TranscriptionJob.status == JobStatus.LEASED,
            TranscriptionJob.lease_expires_at < now,
        ).all()

        for job in stale:
            original_lease_expires_at = job.lease_expires_at
            new_attempts = job.attempts + 1
            new_status = JobStatus.FAILED if new_attempts >= settings.JOB_MAX_ATTEMPTS else JobStatus.QUEUED

            # Optimistic lock: only update if lease_expires_at hasn't changed (no other process grabbed it)
            result = db.execute(
                sa_update(TranscriptionJob)
                .where(
                    TranscriptionJob.id == job.id,
                    TranscriptionJob.status == JobStatus.LEASED,
                    TranscriptionJob.lease_expires_at == original_lease_expires_at,
                )
                .values(
                    status=new_status,
                    attempts=new_attempts,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            if result.rowcount == 0:
                log.debug("Reaper: job %s already handled by another process, skipping", job.id)
                continue

            if new_status == JobStatus.FAILED:
                log.warning("Job %s reached max attempts (%d), marking failed", job.id, new_attempts)
                video = db.query(Video).filter(Video.id == job.video_id).first()
                admin = db.query(User).filter(User.telegram_id != None, User.is_active == True).first()
                if admin and admin.telegram_id and video:
                    asyncio.run(send_failed_job_notification(
                        chat_id=admin.telegram_id,
                        approval_id=0,
                        video_title=video.title,
                        job_id=str(job.id),
                        attempts=new_attempts,
                    ))
            else:
                returned_to_queue += 1
                log.info("Reaper: returning job %s to queued (attempt %d)", job.id, new_attempts)

        db.commit()

    if returned_to_queue:
        log.info("Reaper re-queued %d jobs — triggering GPU start", returned_to_queue)
        task_ensure_gpu_running.apply_async(queue="pipeline")

    log.info("task_reaper done: processed %d stale jobs", len(stale))
