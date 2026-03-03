from __future__ import annotations

import json
import logging
from typing import Protocol

from app.core.config import settings

log = logging.getLogger(__name__)


class HighlightResult:
    def __init__(self, start_sec: float, end_sec: float, score: float, title: str, reason: str):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.score = score
        self.title = title
        self.reason = reason


class LLMProvider(Protocol):
    async def extract_highlights(
        self, transcript: str, prompt: str, clips_count: int
    ) -> list[HighlightResult]: ...


class MockLLMProvider:
    async def extract_highlights(
        self, transcript: str, prompt: str, clips_count: int
    ) -> list[HighlightResult]:
        log.info("MockLLMProvider: returning %d fake highlights", clips_count)
        results = []
        words = transcript.split()
        chunk = max(1, len(words) // (clips_count + 1))
        for i in range(clips_count):
            start = i * 30.0
            end = start + 25.0
            results.append(HighlightResult(
                start_sec=start,
                end_sec=end,
                score=0.9 - i * 0.1,
                title=f"Highlight {i + 1}",
                reason="Mock highlight",
            ))
        return results


class OpenAILLMProvider:
    async def extract_highlights(
        self, transcript: str, prompt: str, clips_count: int
    ) -> list[HighlightResult]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        system_msg = (
            "You are an expert video editor. "
            "Given a video transcript and instructions, identify the most engaging moments. "
            "Return a JSON array of highlight objects."
        )
        user_msg = f"""
Instructions: {prompt}

Transcript:
{transcript[:12000]}

Find exactly {clips_count} highlights. Return ONLY valid JSON array like:
[
  {{"start_sec": 12.5, "end_sec": 45.0, "score": 0.95, "title": "Title", "reason": "Why this is great"}},
  ...
]
The start_sec and end_sec should be seconds from the transcript timestamps.
Each clip should be 20-90 seconds long.
"""
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or "[]"
        # Extract JSON from response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            log.warning("LLM returned no JSON array, raw: %s", raw[:200])
            return []
        data = json.loads(raw[start:end])
        results = []
        for item in data:
            results.append(HighlightResult(
                start_sec=float(item.get("start_sec", 0)),
                end_sec=float(item.get("end_sec", 0)),
                score=float(item.get("score", 0.5)),
                title=item.get("title", ""),
                reason=item.get("reason", ""),
            ))
        return results


def get_llm_provider() -> LLMProvider:
    if settings.LLM_USE_MOCK or not settings.OPENAI_API_KEY:
        return MockLLMProvider()
    return OpenAILLMProvider()
