from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Topic, User
from app.schemas.topic import TopicCreate, TopicRead, TopicUpdate

router = APIRouter(prefix="/topics", tags=["topics"])


def _topic_to_read(t: Topic) -> TopicRead:
    return TopicRead(
        id=t.id,
        name=t.name,
        keywords=json.loads(t.keywords_json or "[]"),
        enabled=t.enabled,
        clips_per_video=t.clips_per_video,
        prompt_for_highlights=t.prompt_for_highlights,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("", response_model=list[TopicRead])
async def list_topics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Topic).order_by(Topic.name))
    return [_topic_to_read(t) for t in result.scalars().all()]


@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
async def create_topic(
    body: TopicCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    topic = Topic(
        id=uuid.uuid4(),
        name=body.name,
        keywords_json=json.dumps(body.keywords, ensure_ascii=False),
        enabled=body.enabled,
        clips_per_video=body.clips_per_video,
        prompt_for_highlights=body.prompt_for_highlights,
        created_at=now,
        updated_at=now,
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return _topic_to_read(topic)


@router.patch("/{topic_id}", response_model=TopicRead)
async def update_topic(
    topic_id: uuid.UUID,
    body: TopicUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    if body.name is not None:
        topic.name = body.name
    if body.keywords is not None:
        topic.keywords_json = json.dumps(body.keywords, ensure_ascii=False)
    if body.enabled is not None:
        topic.enabled = body.enabled
    if body.clips_per_video is not None:
        topic.clips_per_video = body.clips_per_video
    if body.prompt_for_highlights is not None:
        topic.prompt_for_highlights = body.prompt_for_highlights
    topic.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(topic)
    return _topic_to_read(topic)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    await db.delete(topic)
    await db.commit()
