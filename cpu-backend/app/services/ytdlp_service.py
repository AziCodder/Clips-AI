from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

from app.core.config import settings

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

    cookies_file = (settings.YTDLP_COOKIES_FILE or os.environ.get("YTDLP_COOKIES_FILE", "")).strip()
    cmd = ["yt-dlp", "--simulate", "--skip-download", "--print-json", "--no-warnings"]
    # Для dry-run нужны только метаданные — явный формат избегает "Requested format is not available"
    cmd += ["--format", "best/bestvideo+bestaudio/best"]
    if cookies_file and os.path.isfile(cookies_file):
        cmd += ["--cookies", cookies_file]
    else:
        if "youtube" in url.lower() and not cookies_file:
            log.warning("YTDLP_COOKIES_FILE не задан — для YouTube может потребоваться вход (антибот)")
        elif cookies_file and not os.path.isfile(cookies_file):
            log.warning("YTDLP_COOKIES_FILE=%s: файл не найден в контейнере", cookies_file)
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        err = result.stderr or result.stdout
        log.error("yt-dlp dry-run failed: %s", err)
        raise RuntimeError(f"yt-dlp dry-run failed: {err[:800]}")

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


def _find_downloaded_file(output_dir: str, expected_path: str, video_id: str | None) -> str | None:
    """Если файл по ожидаемому пути не найден — ищем в output_dir по id или по расширению."""
    video_extensions = (".mp4", ".mkv", ".webm", ".m4a", ".opus")
    # 1) Ожидаемый путь и варианты расширений
    base = os.path.splitext(expected_path)[0]
    for ext in video_extensions:
        candidate = base + ext
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    if os.path.isfile(expected_path):
        return os.path.abspath(expected_path)
    # 2) Перебор файлов в output_dir: по id в имени или самый новый видео-файл
    if not os.path.isdir(output_dir):
        return None
    candidates: list[tuple[float, str]] = []
    for name in os.listdir(output_dir):
        if name.startswith("."):
            continue
        lower = name.lower()
        if not any(lower.endswith(ext) for ext in video_extensions):
            continue
        path = os.path.join(output_dir, name)
        if not os.path.isfile(path):
            continue
        if video_id and video_id in name:
            return os.path.abspath(path)
        try:
            mtime = os.path.getmtime(path)
            candidates.append((mtime, path))
        except OSError:
            pass
    if not candidates:
        return None
    # Самый новый файл — скорее всего результат мержа
    candidates.sort(key=lambda x: x[0], reverse=True)
    return os.path.abspath(candidates[0][1])


def download_video(
    url: str,
    output_dir: str,
    *,
    cookies_file: str | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> str:
    """Download best quality video+audio to output_dir. Returns path to mp4 file."""
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")
    # Check for cookies file from config/env (used for YouTube anti-bot, VK and other auth-required sites)
    env_cookies = settings.YTDLP_COOKIES_FILE or os.environ.get("YTDLP_COOKIES_FILE", "")
    effective_cookies = cookies_file or (env_cookies if env_cookies and os.path.isfile(env_cookies) else None)

    ydl_opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }

    if progress_callback is not None:
        def _progress_hook(d: dict[str, Any]) -> None:
            status = str(d.get("status") or "")
            if status == "finished":
                progress_callback(100.0, status)
                return
            if status != "downloading":
                return

            pct: float | None = None
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")
            if isinstance(total, (int, float)) and total > 0 and isinstance(downloaded, (int, float)):
                pct = float(downloaded) * 100.0 / float(total)
            else:
                pct_str = d.get("_percent_str")
                if isinstance(pct_str, str):
                    import re
                    cleaned = re.sub(r"[^0-9.]+", "", pct_str)
                    try:
                        pct = float(cleaned)
                    except ValueError:
                        pct = None

            if pct is not None:
                progress_callback(max(0.0, min(100.0, pct)), status)

        ydl_opts["progress_hooks"] = [_progress_hook]

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
                video_id = (info.get("id") or _fallback_id_from_url(url) or "").strip()
                found = _find_downloaded_file(output_dir, video_path, video_id or None)
                if found:
                    log.debug("Downloaded file: %s", found)
                    return found
                raise FileNotFoundError(f"File not found after download: {video_path}")
        except Exception as exc:
            if attempt < max_attempts:
                log.warning("Download attempt %d/%d failed: %s, retrying...", attempt, max_attempts, exc)
                time.sleep(5 * attempt)
                continue
            raise
    raise RuntimeError("download_video: all attempts exhausted")
