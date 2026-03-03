from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from aiogram.types import Update

from app.bot.aiogram_app import bot, dp
from app.core.config import settings

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receive Telegram webhook updates."""
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from e

    try:
        update = Update.model_validate(data)
        await dp.feed_update(bot=bot, update=update)
    except Exception:
        return JSONResponse(status_code=500, content={"ok": False, "detail": "Update processing failed"})

    return {"ok": True}


@router.get("/health")
async def telegram_health():
    return {"status": "ok"}
