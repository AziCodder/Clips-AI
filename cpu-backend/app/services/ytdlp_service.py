from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

log = logging.getLogger(__name__)


def _fallback_id_from_url(url: str) -> str | None:
    """Извлечь id из VK/vkvideo URL, если yt-dlp не вернул id."""
    import re
    m = re.search(r"vk(?:video)?\.ru/video(-?\d+_\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"vk(?:video)?\.ru/video(-?\d+)_(\d+)", url)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return None


def _fallback_source_from_url(url: str) -> str | None:
    if "vkvideo.ru" in url or "vk.com" in url:
        return "vk"
    return None


def dry_run_check(url: str) -> dict[str, Any]:
    """
    Run yt-dlp with --simulate --skip-download --print-json.
    Raises RuntimeError if not downloadable.
    Returns info dict with format/audio/duration validated.
    """
    import json

    cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "")
    cmd = ["yt-dlp", "--simulate", "--skip-download", "--print-json", "--no-warnings"]
    if cookies_file and os.path.isfile(cookies_file):
        cmd += ["--cookies", cookies_file]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        err = result.stderr or result.stdout
        raise RuntimeError(f"yt-dlp dry-run failed: {err[:500]}")

    try:
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(f"yt-dlp dry-run: could not parse JSON: {exc}") from exc

    # Разные сайты (YouTube, VK и др.) отдают поля по-разному — проверяем несколько вариантов.
    duration = info.get("duration") or 0
    if duration is None:
        duration = 0
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0
    if duration < 0:
        duration = 0

    views = info.get("view_count") or info.get("views") or 0
    try:
        views = int(views)
    except (TypeError, ValueError):
        views = 0
    views = max(0, views)

    likes = info.get("like_count") or info.get("likes") or 0
    try:
        likes = int(likes)
    except (TypeError, ValueError):
        likes = 0
    likes = max(0, likes)

    raw_id = info.get("id")
    if raw_id is None:
        raw_id = _fallback_id_from_url(url)
    if raw_id is None:
        raise RuntimeError("yt-dlp did not return video id")
    source_id = str(raw_id)
    source = (info.get("extractor") or _fallback_source_from_url(url) or "youtube").lower()
    if ":" in source:
        source = source.split(":")[0]

    return {
        "source": source,
        "source_id": source_id,
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "channel": (info.get("channel") or info.get("uploader") or info.get("creator") or ""),
        "views": views,
        "likes": likes,
        "duration_sec": int(duration),
        "thumbnail_url": info.get("thumbnail") or "",
        "upload_date": info.get("upload_date"),  # YYYYMMDD
    }


def download_video(url: str, output_dir: str, *, cookies_file: str | None = None) -> str:
    """Download best quality video+audio to output_dir. Returns path to mp4 file."""
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")
    # Check for cookies file from environment (used for VK and other auth-required sites)
    env_cookies = os.environ.get("YTDLP_COOKIES_FILE", "")
    effective_cookies = cookies_file or (env_cookies if os.path.isfile(env_cookies) else None)

    ydl_opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        # Allow any file extension — VK and some sites use unusual extensions
        "allow_unplayable_formats": True,
        "check_formats": False,
    }
    if effective_cookies and os.path.isfile(effective_cookies):
        ydl_opts["cookiefile"] = os.path.abspath(effective_cookies)

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("yt-dlp returned no info")
                video_path = ydl.prepare_filename(info)
                for ext in (".mp4", ".mkv", ".webm", ".m4a"):
                    candidate = os.path.splitext(video_path)[0] + ext
                    if os.path.isfile(candidate):
                        return os.path.abspath(candidate)
                if os.path.isfile(video_path):
                    return os.path.abspath(video_path)
                raise FileNotFoundError(f"File not found after download: {video_path}")
        except Exception as exc:
            if attempt < max_attempts:
                log.warning("Download attempt %d/%d failed: %s, retrying...", attempt, max_attempts, exc)
                time.sleep(5 * attempt)
                continue
            raise
    raise RuntimeError("download_video: all attempts exhausted")
