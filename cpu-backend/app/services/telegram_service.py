from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)


async def send_video_candidate(
    chat_id: int,
    approval_id: int,
    title: str,
    url: str,
    topic_name: str,
    thumbnail_url: str,
    duration_sec: int,
    views: int,
) -> dict[str, Any] | None:
    """Send approval request message with inline buttons to chat_id."""
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        mins = duration_sec // 60
        secs = duration_sec % 60
        caption = (
            f"<b>{title}</b>\n\n"
            f"Тема: {topic_name}\n"
            f"Длительность: {mins}:{secs:02d}\n"
            f"Просмотры: {views:,}\n"
            f"<a href='{url}'>Смотреть</a>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Принять", callback_data=f"approve:{approval_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{approval_id}"),
        ]])
        if thumbnail_url:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=thumbnail_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        return {"message_id": msg.message_id, "chat_id": chat_id}
    except Exception as exc:
        log.error("Failed to send TG candidate: %s", exc)
        return None
    finally:
        await bot.session.close()


async def send_notification(chat_id: int, text: str) -> None:
    from aiogram import Bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        log.error("Failed to send TG notification: %s", exc)
    finally:
        await bot.session.close()


async def send_timeout_notification(
    chat_id: int,
    video_title: str,
    job_id: str,
) -> None:
    """Send notification that a transcription job exceeded the 2-hour limit."""
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        text = (
            f"<b>Задача транскрипции превысила лимит 2 часа</b>\n\n"
            f"Видео: {video_title}\n"
            f"Job ID: <code>{job_id}</code>\n\n"
            f"Задача отменена на GPU и CPU. Выберите действие:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Повторить", callback_data=f"job_retry:{job_id}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"job_delete:{job_id}"),
        ]])
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        log.error("Failed to send timeout notification: %s", exc)
    finally:
        await bot.session.close()


async def send_failed_job_notification(
    chat_id: int,
    approval_id: int,
    video_title: str,
    job_id: str,
    attempts: int,
) -> None:
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        text = (
            f"Job завершился ошибкой {attempts} раз(а)\n"
            f"<b>{video_title}</b>\n"
            f"Job ID: <code>{job_id}</code>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Удалить", callback_data=f"job_delete:{job_id}"),
            InlineKeyboardButton(text="Заменить", callback_data=f"job_replace:{job_id}"),
            InlineKeyboardButton(text="Повторить", callback_data=f"job_retry:{job_id}"),
        ]])
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        log.error("Failed to send job failure notification: %s", exc)
    finally:
        await bot.session.close()
