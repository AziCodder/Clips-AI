"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("telegram_id", sa.BigInteger, nullable=True, unique=True),
        sa.Column("role", sa.String(50), server_default="admin"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "topics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("keywords_json", sa.Text, server_default="[]"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("clips_per_video", sa.Integer, server_default="3"),
        sa.Column("prompt_for_highlights", sa.Text, server_default=""),
        sa.Column("schedule_settings_json", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "videos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_id", UUID(as_uuid=True), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(50), server_default="youtube"),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, server_default=""),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("channel", sa.String(255), server_default=""),
        sa.Column("views", sa.BigInteger, server_default="0"),
        sa.Column("likes", sa.BigInteger, server_default="0"),
        sa.Column("publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(50), server_default="found"),
        sa.Column("thumbnail_url", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_id", name="uq_video_source"),
    )
    op.create_index("ix_video_topic_status", "videos", ["topic_id", "status"])
    op.create_index("ix_video_status_created", "videos", ["status", "created_at"])

    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("s3_key", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, server_default="0"),
        sa.Column("checksum", sa.String(64), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(10), nullable=True),
        sa.Column("decided_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tg_chat_id", sa.BigInteger, nullable=True),
        sa.Column("tg_message_id", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "transcription_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued"),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("s3_audio_key", sa.Text, server_default=""),
        sa.Column("s3_results_prefix", sa.Text, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, server_default=""),
        sa.Column("meta_json", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "highlights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_sec", sa.Float, nullable=False),
        sa.Column("end_sec", sa.Float, nullable=False),
        sa.Column("score", sa.Float, server_default="0"),
        sa.Column("title", sa.Text, server_default=""),
        sa.Column("reason", sa.Text, server_default=""),
        sa.Column("prompt_used", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "clip_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("highlight_id", UUID(as_uuid=True), sa.ForeignKey("highlights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("s3_clip_key", sa.Text, server_default=""),
        sa.Column("ffmpeg_cmd", sa.Text, server_default=""),
        sa.Column("error", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("payload_json", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_json", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stage", "run_date", name="uq_pipeline_run_stage_date"),
    )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
    op.drop_table("notifications")
    op.drop_table("clip_jobs")
    op.drop_table("highlights")
    op.drop_table("transcription_jobs")
    op.drop_table("approvals")
    op.drop_table("assets")
    op.drop_index("ix_video_status_created", "videos")
    op.drop_index("ix_video_topic_status", "videos")
    op.drop_table("videos")
    op.drop_table("topics")
    op.drop_table("users")
