from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Highlight, User
from app.schemas.highlight import HighlightRead

router = APIRouter(prefix="/highlights", tags=["highlights"])


@router.get("/{video_id}", response_model=list[HighlightRead])
async def list_highlights(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Highlight).where(Highlight.video_id == video_id).order_by(Highlight.score.desc())
    )
    return result.scalars().all()
