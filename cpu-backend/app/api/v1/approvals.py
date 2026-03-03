from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Approval, ApprovalStatus, User, Video, VideoStatus
from app.schemas.approval import ApprovalDecisionRequest, ApprovalRead

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{video_id}", response_model=ApprovalRead)
async def decide_approval(
    video_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")

    result = await db.execute(select(Approval).where(Approval.video_id == video_id))
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Already decided: {approval.status}")

    approval.status = body.status
    approval.decided_at = datetime.now(timezone.utc)
    approval.decided_by = "web"
    approval.decided_by_user_id = current_user.id

    video_result = await db.execute(select(Video).where(Video.id == video_id))
    video = video_result.scalar_one_or_none()
    if video:
        video.status = VideoStatus.APPROVED if body.status == ApprovalStatus.APPROVED else VideoStatus.REJECTED

    await db.commit()
    await db.refresh(approval)
    return approval
