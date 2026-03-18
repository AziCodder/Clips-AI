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
            "You are an expert viral short-form video editor specializing in hooks and attention retention. "
            "Your goal is to find moments that will STOP someone mid-scroll and make them watch to the end. "
            "CRITICAL RULE: The FIRST clip in your list MUST be the single strongest hook from the ENTIRE transcript — "
            "a moment that creates immediate curiosity, tension, surprise, or an emotional reaction in the first 3 seconds. "
            "Strong hook patterns: shocking statement, unanswered question, unexpected reveal, "
            "emotional peak, contrarian take, or a moment that makes viewer think 'wait, what?'. "
            "Remaining clips should also be highly engaging and self-contained (watchable without context). "
            "Return a JSON array of highlight objects, sorted by hook_strength DESC."
        )

        # Smart truncation: keep beginning + end for full context
        max_chars = 20000
        if len(transcript) > max_chars:
            half = max_chars // 2
            transcript_trimmed = (
                transcript[:half]
                + "\n\n[... middle section omitted for brevity ...]\n\n"
                + transcript[-half:]
            )
        else:
            transcript_trimmed = transcript

        user_msg = f"""Instructions: {prompt}

Transcript (with timestamps):
{transcript_trimmed}

Find exactly {clips_count} clips. The FIRST clip MUST be the strongest hook from anywhere in the transcript.
Return ONLY a valid JSON array:
[
  {{"start_sec": 12.5, "end_sec": 45.0, "score": 0.95, "title": "Hook title", "reason": "Why this stops the scroll"}},
  ...
]
Rules:
- start_sec / end_sec must match actual timestamps in the transcript
- Each clip: 20-90 seconds long
- First clip: strongest possible hook (shocking, surprising, or emotionally charged)
- Score 0.0-1.0 where 1.0 = viral-ready hook
- No duplicate time ranges
"""
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content or "[]"
        # Extract JSON array from response (handles markdown code fences)
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            log.warning("LLM returned no JSON array, raw: %s", raw[:200])
            return []
        try:
            data = json.loads(raw[start:end])
        except json.JSONDecodeError as exc:
            log.warning("LLM JSON parse error: %s | raw: %s", exc, raw[:300])
            return []
        results = []
        for item in data:
            try:
                results.append(HighlightResult(
                    start_sec=float(item.get("start_sec", 0)),
                    end_sec=float(item.get("end_sec", 0)),
                    score=float(item.get("score", 0.5)),
                    title=str(item.get("title", "")),
                    reason=str(item.get("reason", "")),
                ))
            except (TypeError, ValueError) as exc:
                log.warning("Skipping malformed highlight item %s: %s", item, exc)
        return results


def get_llm_provider() -> LLMProvider:
    if settings.LLM_USE_MOCK or not settings.OPENAI_API_KEY:
        return MockLLMProvider()
    return OpenAILLMProvider()
