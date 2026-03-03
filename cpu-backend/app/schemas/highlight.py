from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class HighlightRead(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    start_sec: float
    end_sec: float
    score: float
    title: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ClipRead(BaseModel):
    id: uuid.UUID
    highlight_id: uuid.UUID
    status: str
    s3_clip_key: str
    created_at: datetime
    presigned_url: str | None = None

    model_config = {"from_attributes": True}
