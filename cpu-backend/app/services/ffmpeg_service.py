from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app.core.config import settings

log = logging.getLogger(__name__)


def extract_audio_flac(video_path: str, output_dir: str) -> str:
    """Extract 16kHz mono FLAC audio from video. Returns path to .flac file."""
    os.makedirs(output_dir, exist_ok=True)
    base = Path(video_path).stem
    out_path = os.path.join(output_dir, f"{base}_audio.flac")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",
        "-acodec", "flac",
        "-ar", "16000",
        "-ac", "1",
        out_path,
    ]
    log.info("Extracting audio: %s -> %s", video_path, out_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {result.stderr[:500]}")
    if not os.path.isfile(out_path):
        raise FileNotFoundError(f"ffmpeg did not create: {out_path}")
    return os.path.abspath(out_path)


def cut_clip(
    video_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
    *,
    vertical: bool = True,
) -> str:
    """
    Cut a clip from video_path [start_sec, end_sec] and save to output_path.
    If vertical=True, center-crop to 9:16 (no AI).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end_sec - start_sec

    if vertical:
        # Center-crop to 9:16 ratio without AI
        vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"
    else:
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", str(settings.FFMPEG_THREADS),
        "-movflags", "+faststart",
        output_path,
    ]
    log.info("Cutting clip: %s [%.1f-%.1f] -> %s", video_path, start_sec, end_sec, output_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg clip cut failed: {result.stderr[:500]}")
    if not os.path.isfile(output_path):
        raise FileNotFoundError(f"ffmpeg did not create clip: {output_path}")
    return os.path.abspath(output_path)


def get_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:300]}")
    import json
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))
