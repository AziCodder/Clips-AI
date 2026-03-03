"""
Entry point for running the Telegram bot in long-polling mode.
Used by the 'bot' Docker service — does not require a public HTTPS URL.

Usage:
    python -m app.bot.run_polling
"""
from __future__ import annotations

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    from app.bot.aiogram_app import bot, dp

    # Remove any previously set webhook so polling can work
    await bot.delete_webhook(drop_pending_updates=False)
    log.info("Webhook removed. Starting polling...")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        await bot.session.close()
        log.info("Bot session closed.")


if __name__ == "__main__":
    asyncio.run(main())
