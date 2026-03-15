from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VideoStatus:
    FOUND = "found"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    AUDIO_READY = "audio_ready"
    QUEUED_GPU = "queued_gpu"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    CLIPS_RENDERING = "clips_rendering"
    CLIPS_READY = "clips_ready"
    FAILED = "failed"


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_video_source"),
        Index("ix_video_topic_status", "topic_id", "status"),
        Index("ix_video_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="youtube")
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(255), default="")
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default=VideoStatus.FOUND)
    download_progress_pct: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    topic: Mapped["Topic"] = relationship(back_populates="videos")  # type: ignore[name-defined]
    assets: Mapped[list["Asset"]] = relationship(back_populates="video", cascade="all, delete-orphan")  # type: ignore[name-defined]
    approval: Mapped["Approval | None"] = relationship(back_populates="video", uselist=False)  # type: ignore[name-defined]
    transcription_jobs: Mapped[list["TranscriptionJob"]] = relationship(back_populates="video", cascade="all, delete-orphan")  # type: ignore[name-defined]
    highlights: Mapped[list["Highlight"]] = relationship(back_populates="video", cascade="all, delete-orphan")  # type: ignore[name-defined]
