"""add video download_progress_pct

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("download_progress_pct", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "download_progress_pct")
