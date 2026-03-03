from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1 import (
    auth,
    topics,
    videos,
    media,
    highlights,
    gpu_internal,
    telegram_webhook,
    approvals,
    transcription_queue,
    health,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bot runs in a separate polling service (see docker-compose bot service).
    # Webhook setup is skipped to avoid conflicting with polling mode.
    yield
    try:
        from app.bot.aiogram_app import bot
        await bot.session.close()
    except Exception:
        log.warning("Failed to close bot session on shutdown", exc_info=True)


app = FastAPI(
    title="Clips API",
    version="1.0.0",
    docs_url="/api/docs" if settings.ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

_cors_origins: list[str]
if settings.ENV != "production":
    _cors_origins = ["*"]
else:
    _cors_origins = [settings.FRONTEND_ORIGIN] if settings.FRONTEND_ORIGIN else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(topics.router, prefix=PREFIX)
app.include_router(videos.router, prefix=PREFIX)
app.include_router(media.router, prefix=PREFIX)
app.include_router(highlights.router, prefix=PREFIX)
app.include_router(approvals.router, prefix=PREFIX)
app.include_router(transcription_queue.router, prefix=PREFIX)
app.include_router(gpu_internal.router, prefix=PREFIX)
app.include_router(telegram_webhook.router, prefix=PREFIX)
app.include_router(health.router, prefix=PREFIX)
