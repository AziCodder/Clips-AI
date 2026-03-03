from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.base import get_db
from app.db.models import User

security = HTTPBearer()


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    from sqlalchemy import select

    token = credentials.credentials
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def verify_gpu_api_key(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Verify GPU internal API key and IP allowlist."""
    # Check Bearer key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing GPU API key")
    token = authorization[7:]
    if token != settings.GPU_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid GPU API key")

    # Check IP allowlist
    allowlist = settings.gpu_ip_allowlist_set
    if allowlist:
        client_ip = request.client.host if request.client else ""
        # Also check X-Forwarded-For
        forwarded = request.headers.get("x-forwarded-for", "")
        ips = {client_ip} | {ip.strip() for ip in forwarded.split(",") if ip.strip()}
        if not ips.intersection(allowlist):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")
