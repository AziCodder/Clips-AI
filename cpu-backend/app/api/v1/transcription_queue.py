from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import JobStatus, TranscriptionJob, User
from app.services import s3_service

router = APIRouter(prefix="/transcription-jobs", tags=["transcription-queue"])


class JobRead(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    status: str
    priority: int
    attempts: int
    created_at: datetime

    model_config = {"from_attributes": True}


class JobPatch(BaseModel):
    priority: int | None = None


@router.get("", response_model=list[JobRead])
async def list_jobs(
    video_id: uuid.UUID | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(TranscriptionJob)
    if video_id:
        stmt = stmt.where(TranscriptionJob.video_id == video_id)
    if job_status:
        stmt = stmt.where(TranscriptionJob.status == job_status)
    stmt = stmt.order_by(TranscriptionJob.priority.desc(), TranscriptionJob.created_at.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/{job_id}", response_model=JobRead)
async def update_job_priority(
    job_id: uuid.UUID,
    body: JobPatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.QUEUED:
        raise HTTPException(status_code=400, detail="Can only update priority of queued jobs")
    if body.priority is not None:
        job.priority = body.priority
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.QUEUED:
        # Delete transcript artifacts from S3
        s3_service.delete_prefix(f"videos/{job.video_id}/transcripts/{job.id}/")
        await db.delete(job)
        await db.commit()

    elif job.status in (JobStatus.LEASED, JobStatus.STARTED):
        # Mark as cancelled — GPU will stop after current operation
        job.status = JobStatus.CANCELLED
        await db.commit()
        # S3 cleanup happens after GPU confirms
    else:
        raise HTTPException(status_code=400, detail=f"Cannot delete job in status '{job.status}'")
