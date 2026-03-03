from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    clips_per_video: int = Field(default=3, ge=1, le=20)
    prompt_for_highlights: str = ""


class TopicUpdate(BaseModel):
    name: str | None = None
    keywords: list[str] | None = None
    enabled: bool | None = None
    clips_per_video: int | None = Field(default=None, ge=1, le=20)
    prompt_for_highlights: str | None = None


class TopicRead(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    enabled: bool
    clips_per_video: int
    prompt_for_highlights: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
