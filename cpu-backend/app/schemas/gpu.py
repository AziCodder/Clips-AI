from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class GpuJobNextResponse(BaseModel):
    job_id: uuid.UUID
    video_id: uuid.UUID
    s3_audio_key: str
    language_hint: str | None = None
    batch_size: int = 8
    compute_type: str = "float16"
    results_prefix: str


class GpuJobStartedRequest(BaseModel):
    worker_id: str
    started_at: datetime


class GpuJobCompletedRequest(BaseModel):
    worker_id: str
    s3_prefix_results: str
    duration_sec: float
    detected_language: str | None = None
    meta: dict = {}


class GpuJobFailedRequest(BaseModel):
    worker_id: str
    error_type: str
    traceback: str
    retryable: bool = True


class GpuJobAckResponse(BaseModel):
    ack: bool
    reason: str = ""


class GpuCancelRequest(BaseModel):
    worker_id: str
