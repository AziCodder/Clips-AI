from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatus:
    QUEUED = "queued"
    LEASED = "leased"
    STARTED = "started"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    CLEANUP_DONE = "cleanup_done"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.QUEUED)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher = picked first
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    s3_audio_key: Mapped[str] = mapped_column(Text, default="")
    s3_results_prefix: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    video: Mapped["Video"] = relationship(back_populates="transcription_jobs")  # type: ignore[name-defined]
