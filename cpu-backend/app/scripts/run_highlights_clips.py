"""
Скрипт запуска пайплайна по локальным файлам: транскрипт + видео → ИИ подбор моментов → нарезка клипов.

Запуск из корня cpu-backend (нужен .env с настройками, в т.ч. LLM_USE_MOCK=1 или OPENAI_API_KEY):

  python -m app.scripts.run_highlights_clips --text путь/к/transcript.txt --video путь/к/video.mp4 --output-dir путь/к/clips

Опции:
  --prompt     Промпт для ИИ (по умолчанию: выбери лучшие моменты для клипов).
  --clips      Количество клипов (по умолчанию 3).
  --no-vertical  Не обрезать в 9:16 (оставить исходные пропорции).
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Подбор лучших моментов по транскрипту (ИИ) и нарезка клипов из видео."
    )
    parser.add_argument("--text", required=True, help="Путь к файлу транскрипта (.txt)")
    parser.add_argument("--video", required=True, help="Путь к файлу видео")
    parser.add_argument("--output-dir", required=True, help="Папка для сохранения клипов")
    parser.add_argument("--prompt", default="", help="Промпт для ИИ")
    parser.add_argument("--clips", type=int, default=3, help="Количество клипов (по умолчанию 3)")
    parser.add_argument("--no-vertical", action="store_true", help="Не обрезать в вертикальный 9:16")
    args = parser.parse_args()

    from app.services.highlights_runner import run_highlights_and_clips_from_files

    try:
        paths = run_highlights_and_clips_from_files(
            args.text,
            args.video,
            args.output_dir,
            prompt=args.prompt or "Выбери самые ценные моменты для коротких клипов.",
            clips_count=args.clips,
            vertical=not args.no_vertical,
        )
        print(f"Готово. Создано клипов: {len(paths)}")
        for p in paths:
            print(f"  {p}")
    except FileNotFoundError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.exception("Ошибка при нарезке")
        sys.exit(1)


if __name__ == "__main__":
    main()
