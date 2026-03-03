from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from app.core.config import settings
from app.bot.handlers.approvals import router as approvals_router

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
dp.include_router(approvals_router)


async def setup_webhook() -> None:
    webhook_url = f"{settings.TELEGRAM_WEBHOOK_BASE_URL}/api/v1/telegram/webhook"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
        allowed_updates=["message", "callback_query"],
    )


async def remove_webhook() -> None:
    await bot.delete_webhook()
