from __future__ import annotations

from pydantic import BaseModel


class WordEntry(BaseModel):
    word: str
    start: float
    end: float


class SegmentEntry(BaseModel):
    start: float
    end: float
    text: str


class TranscriptRead(BaseModel):
    text: str
    words: list[WordEntry]
    segments: list[SegmentEntry]
    language: str | None = None
    job_id: str | None = None
