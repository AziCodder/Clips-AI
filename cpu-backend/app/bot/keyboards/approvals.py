from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def approval_keyboard(approval_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять", callback_data=f"approve:{approval_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{approval_id}"),
    ]])


def job_action_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Удалить", callback_data=f"job_delete:{job_id}"),
        InlineKeyboardButton(text="Заменить", callback_data=f"job_replace:{job_id}"),
        InlineKeyboardButton(text="Повторить", callback_data=f"job_retry:{job_id}"),
    ]])
