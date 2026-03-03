from __future__ import annotations

from pydantic import BaseModel


class PresignedUrlResponse(BaseModel):
    url: str
    expires_in_sec: int
    asset_type: str
