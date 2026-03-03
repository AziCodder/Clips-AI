from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

log = logging.getLogger(__name__)

router = Router()


# ── Sync DB helpers (run via asyncio.to_thread) ───────────────────────────────

def _sync_get_user_info(tg_id: int) -> str:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.db.models import User

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        user = db.query(User).filter(User.telegram_id == tg_id).first()
        if user:
            return f"Ваш аккаунт привязан к email: {user.email}\nTelegram ID: <code>{tg_id}</code>"
        return f"Ваш Telegram ID: <code>{tg_id}</code>\n\nДля привязки укажите этот ID при регистрации на сайте."


def _sync_get_queue_stats() -> str:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.db.models import TranscriptionJob, JobStatus

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        queued = db.query(TranscriptionJob).filter(TranscriptionJob.status == JobStatus.QUEUED).count()
        running = db.query(TranscriptionJob).filter(TranscriptionJob.status == JobStatus.STARTED).count()
        done = db.query(TranscriptionJob).filter(TranscriptionJob.status == JobStatus.ACKNOWLEDGED).count()
        failed = db.query(TranscriptionJob).filter(TranscriptionJob.status == JobStatus.FAILED).count()
    return (
        "<b>Очередь транскрибации:</b>\n"
        f"В очереди: {queued}\n"
        f"В работе: {running}\n"
        f"Готово: {done}\n"
        f"Ошибок: {failed}"
    )


def _sync_get_today_stats() -> str:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.db.models import Video, VideoStatus
    from datetime import date

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        today = date.today()
        pending = db.query(Video).filter(Video.status == VideoStatus.PENDING_APPROVAL).count()
        approved = db.query(Video).filter(Video.status == VideoStatus.APPROVED).count()
        downloaded = db.query(Video).filter(Video.status == VideoStatus.AUDIO_READY).count()
        transcribed = db.query(Video).filter(Video.status == VideoStatus.TRANSCRIBED).count()
        clips_ready = db.query(Video).filter(Video.status == VideoStatus.CLIPS_READY).count()
    return (
        f"<b>Сводка за {today}:</b>\n"
        f"Ожидают подтверждения: {pending}\n"
        f"Подтверждено: {approved}\n"
        f"Скачано: {downloaded}\n"
        f"Транскрибировано: {transcribed}\n"
        f"Клипы готовы: {clips_ready}"
    )


def _sync_handle_approval(approval_id: int, action: str, tg_user_id: int | None) -> str:
    """
    Returns one of:
      "not_found", "already:<status>", "approve", "reject"
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.db.models import Approval, Video, VideoStatus, ApprovalStatus, User

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        approval = db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval:
            return "not_found"
        if approval.status != ApprovalStatus.PENDING:
            return f"already:{approval.status}"

        user = (
            db.query(User).filter(User.telegram_id == tg_user_id).first()
            if tg_user_id else None
        )

        approval.status = ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
        approval.decided_at = datetime.now(timezone.utc)
        approval.decided_by = "tg"
        if user:
            approval.decided_by_user_id = user.id

        video = db.query(Video).filter(Video.id == approval.video_id).first()
        if video:
            video.status = VideoStatus.APPROVED if action == "approve" else VideoStatus.REJECTED

        db.commit()
    return action


def _sync_handle_job(action: str, job_id: uuid.UUID | None) -> str:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.db.models import TranscriptionJob, JobStatus, Video, VideoStatus
    from app.services import s3_service

    if not job_id:
        return "not_found"

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as db:
        job = db.query(TranscriptionJob).filter(TranscriptionJob.id == job_id).first()
        if not job:
            return "not_found"

        if action == "job_retry":
            job.attempts = 0
            job.lease_expires_at = None
            job.lease_owner = None
            job.error = ""
            job.status = JobStatus.QUEUED
            # Ensure video is in the correct state for GPU processing
            video = db.query(Video).filter(Video.id == job.video_id).first()
            if video and video.status not in (VideoStatus.QUEUED_GPU,):
                video.status = VideoStatus.QUEUED_GPU
            db.commit()
            return "retried"

        elif action == "job_delete":
            video_id = job.video_id
            try:
                s3_service.delete_prefix(f"videos/{job.video_id}/transcripts/{job.id}/")
            except Exception:
                pass
            db.delete(job)
            # Reset video so it can be re-queued later if needed
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.status = VideoStatus.AUDIO_READY
            db.commit()
            return "deleted"

        elif action == "job_replace":
            return "replace"

    return "unknown"


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    tg_id = message.from_user.id if message.from_user else None
    if not tg_id:
        await message.answer("Не удалось определить Telegram ID.")
        return
    text = await asyncio.to_thread(_sync_get_user_info, tg_id)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("queue"))
async def cmd_queue(message: Message):
    text = await asyncio.to_thread(_sync_get_queue_stats)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("today"))
async def cmd_today(message: Message):
    text = await asyncio.to_thread(_sync_get_today_stats)
    await message.answer(text, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith(("approve:", "reject:")))
async def handle_approval_callback(callback: CallbackQuery):
    """Handle approve/reject buttons from video candidate messages."""
    try:
        data = callback.data or ""
        action, approval_id_str = data.split(":", 1)
        approval_id = int(approval_id_str)
        tg_user_id = callback.from_user.id if callback.from_user else None

        # Run sync DB work in a thread so the event loop stays responsive
        result = await asyncio.to_thread(_sync_handle_approval, approval_id, action, tg_user_id)

        if result == "not_found":
            await callback.answer("Решение не найдено", show_alert=True)
            return

        if result.startswith("already:"):
            status_val = result[8:]
            await callback.answer(f"Уже решено: {status_val}", show_alert=True)
            return

        label = "✅ Принято" if action == "approve" else "❌ Отклонено"
        await callback.answer(label)

        # After approval — immediately start the download pipeline
        if action == "approve":
            try:
                import app.tasks.celery_app  # ensure Celery app + routes are loaded  # noqa: F401
                from app.tasks.pipeline_tasks import task_download_approved
                task_download_approved.apply_async(queue="pipeline")
                log.info("task_download_approved triggered after TG approval %d", approval_id)
            except Exception as exc:
                log.warning("Could not trigger task_download_approved: %s", exc)

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        log.info("Approval %d %s by TG user %s", approval_id, action, tg_user_id)

    except Exception:
        log.exception("handle_approval_callback error")
        try:
            await callback.answer("Ошибка сервера. Попробуйте позже.", show_alert=True)
        except Exception:
            pass


@router.callback_query(lambda c: c.data and c.data.startswith("job_"))
async def handle_job_callback(callback: CallbackQuery):
    """Handle job failure action buttons: retry/delete/replace."""
    try:
        data = callback.data or ""
        parts = data.split(":", 1)
        action = parts[0]
        job_id_str = parts[1] if len(parts) > 1 else ""
        job_id = uuid.UUID(job_id_str) if job_id_str else None

        result = await asyncio.to_thread(_sync_handle_job, action, job_id)

        if result == "not_found":
            await callback.answer("Job не найден", show_alert=True)
            return

        messages = {
            "retried": "Job поставлен в очередь повторно",
            "deleted": "Job удалён",
            "replace": "Добавьте новое видео вручную через сайт",
        }
        await callback.answer(messages.get(result, "Готово"))

        # After retry — ensure GPU is running to pick up the re-queued job
        if result == "retried":
            try:
                import app.tasks.celery_app  # noqa: F401
                from app.tasks.pipeline_tasks import task_ensure_gpu_running
                task_ensure_gpu_running.apply_async(queue="pipeline")
                log.info("task_ensure_gpu_running triggered after job retry %s", job_id_str)
            except Exception as exc:
                log.warning("Could not trigger task_ensure_gpu_running: %s", exc)

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    except Exception:
        log.exception("handle_job_callback error")
        try:
            await callback.answer("Ошибка сервера. Попробуйте позже.", show_alert=True)
        except Exception:
            pass
