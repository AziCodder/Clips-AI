from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class ApprovalDecisionRequest(BaseModel):
    status: str  # "approved" | "rejected"


class ApprovalRead(BaseModel):
    id: int
    video_id: uuid.UUID
    status: str
    decided_at: datetime | None
    decided_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
