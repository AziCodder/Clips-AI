from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.ytdlp_service import dry_run_check

log = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


async def search_youtube_api(
    query: str,
    *,
    max_results: int = 10,
    min_views: int = 10_000,
    min_duration_sec: int = 120,
    max_duration_sec: int = 7200,
    published_after: datetime | None = None,
) -> list[dict[str, Any]]:
    """Search YouTube Data API v3. Returns filtered candidate dicts."""
    if not settings.YOUTUBE_DATA_API_KEY:
        log.warning("YOUTUBE_DATA_API_KEY not set, skipping API search")
        return []

    if published_after is None:
        published_after = datetime.now(timezone.utc) - timedelta(days=30)

    async with httpx.AsyncClient(timeout=30) as client:
        search_resp = await client.get(
            YOUTUBE_SEARCH_URL,
            params={
                "part": "id",
                "q": query,
                "type": "video",
                "maxResults": max_results,
                "publishedAfter": published_after.isoformat().replace("+00:00", "Z"),
                "key": settings.YOUTUBE_DATA_API_KEY,
                "videoDuration": "medium",  # 4-20 min; use "long" for >20
                "videoEmbeddable": "true",
            },
        )
    if search_resp.status_code != 200:
        log.warning("YouTube search API error %s: %s", search_resp.status_code, search_resp.text[:200])
        return []

    video_ids = [item["id"]["videoId"] for item in search_resp.json().get("items", [])]
    if not video_ids:
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        details_resp = await client.get(
            YOUTUBE_VIDEOS_URL,
            params={
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(video_ids),
                "key": settings.YOUTUBE_DATA_API_KEY,
            },
        )
    if details_resp.status_code != 200:
        return []

    results = []
    for item in details_resp.json().get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        views = int(stats.get("viewCount", 0) or 0)
        duration_sec = _parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
        if views < min_views:
            continue
        if not (min_duration_sec <= duration_sec <= max_duration_sec):
            continue
        results.append({
            "source": "youtube",
            "source_id": item["id"],
            "url": f"https://www.youtube.com/watch?v={item['id']}",
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel": snippet.get("channelTitle", ""),
            "views": views,
            "likes": int(stats.get("likeCount", 0) or 0),
            "duration_sec": duration_sec,
            "thumbnail_url": (snippet.get("thumbnails", {}).get("high", {}) or {}).get("url", ""),
            "publish_date": snippet.get("publishedAt"),
        })
    return results


async def search_ytdlp_fallback(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Fallback: use yt-dlp ytsearch."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ytdlp_search_sync, query, max_results)


def _ytdlp_search_sync(query: str, max_results: int) -> list[dict[str, Any]]:
    import yt_dlp
    results = []
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": f"ytsearch{max_results}",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            for entry in (info or {}).get("entries", []):
                if not entry:
                    continue
                results.append({
                    "source": "youtube",
                    "source_id": entry.get("id", ""),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "title": entry.get("title", ""),
                    "description": "",
                    "channel": entry.get("channel") or entry.get("uploader", ""),
                    "views": entry.get("view_count", 0) or 0,
                    "likes": 0,
                    "duration_sec": int(entry.get("duration") or 0),
                    "thumbnail_url": entry.get("thumbnail", ""),
                    "publish_date": None,
                })
        except Exception as exc:
            log.warning("yt-dlp fallback search failed: %s", exc)
    return results


async def run_dry_run(url: str) -> dict[str, Any]:
    """Async wrapper around yt-dlp dry-run check."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, dry_run_check, url)


def _parse_iso8601_duration(s: str) -> int:
    """Parse ISO 8601 duration like PT1H2M3S -> seconds."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    h, mi, sec = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + sec
