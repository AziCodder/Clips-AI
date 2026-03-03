"""
Запуск пайплайна «текст → ИИ (подбор моментов) → нарезка клипов» по локальным файлам.
Без БД и S3: путь к транскрипту, путь к видео, папка для клипов.
"""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)


def run_highlights_and_clips_from_files(
    text_path: str,
    video_path: str,
    output_dir: str,
    *,
    prompt: str = "",
    clips_count: int = 3,
    vertical: bool = True,
) -> list[str]:
    """
    По файлу транскрипта и видео: ИИ выбирает лучшие моменты, ffmpeg нарезает клипы.

    - text_path: путь к .txt с транскриптом (как от WhisperX / transcribe_video.py).
    - video_path: путь к видео (mp4 и т.д.).
    - output_dir: папка, куда сохранить клипы (clip_1.mp4, clip_2.mp4, ...).
    - prompt: промпт для ИИ (например: «Найди самые эмоциональные моменты»).
    - clips_count: сколько клипов выбрать.
    - vertical: резать в вертикальном формате 9:16.

    Возвращает список путей к созданным файлам клипов.
    """
    if not os.path.isfile(text_path):
        raise FileNotFoundError(f"Файл транскрипта не найден: {text_path}")
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Файл видео не найден: {video_path}")

    os.makedirs(output_dir, exist_ok=True)

    with open(text_path, "r", encoding="utf-8", errors="replace") as f:
        transcript = f.read()

    if not transcript.strip():
        raise ValueError("Файл транскрипта пуст")

    from app.services.llm.provider import get_llm_provider
    from app.services.ffmpeg_service import cut_clip

    provider = get_llm_provider()
    highlights = asyncio.run(
        provider.extract_highlights(transcript, prompt or "Выбери самые ценные моменты для клипов.", clips_count)
    )

    out_paths: list[str] = []
    for i, h in enumerate(highlights):
        if h.end_sec <= h.start_sec:
            log.warning("Пропуск некорректного интервала %.1f–%.1f", h.start_sec, h.end_sec)
            continue
        clip_path = os.path.join(output_dir, f"clip_{i + 1}.mp4")
        try:
            cut_clip(video_path, h.start_sec, h.end_sec, clip_path, vertical=vertical)
            out_paths.append(os.path.abspath(clip_path))
        except Exception as e:
            log.error("Ошибка нарезки клипа %s: %s", clip_path, e)
            raise

    log.info("Создано клипов: %d в %s", len(out_paths), output_dir)
    return out_paths
