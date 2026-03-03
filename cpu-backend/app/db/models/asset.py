from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AssetType:
    MASTER_VIDEO = "master_video"
    THUMB = "thumb"
    AUDIO = "audio"
    TRANSCRIPT_TXT = "transcript_txt"
    TRANSCRIPT_WORDS = "transcript_words"
    TRANSCRIPT_SEGMENTS = "transcript_segments"
    SUBTITLE_SRT = "subtitle_srt"
    CLIP_VIDEO = "clip_video"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    video: Mapped["Video"] = relationship(back_populates="assets")  # type: ignore[name-defined]
