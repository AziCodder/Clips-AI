from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field


class VideoManualCreate(BaseModel):
    url: str = Field(description="YouTube URL")
    topic_id: uuid.UUID | None = None
    auto_approve: bool = Field(default=False, description="Сразу одобрить и запустить скачивание (без ожидания в Telegram)")


class VideoRead(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID | None
    source: str
    source_id: str
    url: str
    title: str
    channel: str
    views: int
    duration_sec: int
    status: str
    thumbnail_url: str
    created_at: datetime
    already_exists: bool = False

    model_config = {"from_attributes": True}


class VideoDetailRead(VideoRead):
    description: str
    likes: int
    publish_date: datetime | None


class VideoListResponse(BaseModel):
    items: list[VideoRead]
    total: int
    page: int
    page_size: int
