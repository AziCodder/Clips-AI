from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Asset, AssetType, ClipJob, ClipJobStatus, Highlight, TranscriptionJob, User, Video
from app.schemas.highlight import ClipRead, HighlightRead
from app.schemas.media import PresignedUrlResponse
from app.schemas.transcript import SegmentEntry, TranscriptRead, WordEntry
from app.services import s3_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/presigned", response_model=PresignedUrlResponse)
async def get_presigned(
    video_id: uuid.UUID = Query(...),
    asset_type: str = Query(...),
    clip_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if asset_type == AssetType.CLIP_VIDEO:
        if not clip_id:
            raise HTTPException(status_code=400, detail="clip_id required for clip_video")
        result = await db.execute(
            select(ClipJob)
            .join(Highlight, ClipJob.highlight_id == Highlight.id)
            .where(ClipJob.id == clip_id, Highlight.video_id == video_id)
        )
        clip = result.scalar_one_or_none()
        if not clip or not clip.s3_clip_key:
            raise HTTPException(status_code=404, detail="Clip not found")
        url = s3_service.presign_url(clip.s3_clip_key)
        return PresignedUrlResponse(url=url, expires_in_sec=3600, asset_type=asset_type)

    result = await db.execute(
        select(Asset).where(Asset.video_id == video_id, Asset.type == asset_type)
    )
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_type}' not found")
    url = s3_service.presign_url(asset.s3_key)
    return PresignedUrlResponse(url=url, expires_in_sec=3600, asset_type=asset_type)


# ── Transcript ────────────────────────────────────────────────────────────────

@router.get("/videos/{video_id}/transcript", response_model=TranscriptRead)
async def get_transcript(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Get latest acknowledged job
    result = await db.execute(
        select(TranscriptionJob)
        .where(TranscriptionJob.video_id == video_id, TranscriptionJob.status == "acknowledged")
        .order_by(TranscriptionJob.finished_at.desc())
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Transcript not available")

    try:
        txt = s3_service.download_fileobj(f"videos/{video_id}/transcripts/{job.id}/transcript.txt").decode("utf-8")
        words_raw = json.loads(s3_service.download_fileobj(f"videos/{video_id}/transcripts/{job.id}/words.json"))
        segs_raw = json.loads(s3_service.download_fileobj(f"videos/{video_id}/transcripts/{job.id}/segments.json"))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Transcript files missing: {exc}")

    return TranscriptRead(
        text=txt,
        words=[WordEntry(**w) for w in words_raw],
        segments=[SegmentEntry(**s) for s in segs_raw],
        job_id=str(job.id),
    )


# ── Highlights ────────────────────────────────────────────────────────────────

@router.get("/videos/{video_id}/highlights", response_model=list[HighlightRead])
async def get_highlights(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Highlight).where(Highlight.video_id == video_id).order_by(Highlight.score.desc())
    )
    return result.scalars().all()


# ── Clips ─────────────────────────────────────────────────────────────────────

@router.get("/videos/{video_id}/clips", response_model=list[ClipRead])
async def get_clips(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    highlights_result = await db.execute(
        select(Highlight).where(Highlight.video_id == video_id)
    )
    highlight_ids = [h.id for h in highlights_result.scalars().all()]

    if not highlight_ids:
        return []

    clips_result = await db.execute(
        select(ClipJob).where(
            ClipJob.highlight_id.in_(highlight_ids),
            ClipJob.status == ClipJobStatus.DONE,
        )
    )
    clips = clips_result.scalars().all()

    result = []
    for clip in clips:
        presigned = None
        if clip.s3_clip_key:
            try:
                presigned = s3_service.presign_url(clip.s3_clip_key)
            except Exception:
                log.warning("Failed to presign clip URL for clip_id=%s", clip.id, exc_info=True)
        result.append(ClipRead(
            id=clip.id,
            highlight_id=clip.highlight_id,
            status=clip.status,
            s3_clip_key="",  # never expose raw key to frontend
            created_at=clip.created_at,
            presigned_url=presigned,
        ))
    return result
