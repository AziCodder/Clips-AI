#!/usr/bin/env python3
"""
Production-ready скрипт транскрипции видео.
Скачивает видео (YouTube, Instagram, TikTok, прямые ссылки), извлекает аудио,
распознаёт речь Whisper large-v3 и выравнивает по словам через WhisperX.
Выход: .txt, .json (word/start/end), .srt. Полностью офлайн, без платных API.
"""

import argparse
import gc
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# -----------------------------------------------------------------------------
# Проверка и импорт зависимостей
# -----------------------------------------------------------------------------


def _check_imports():
    """Проверяет наличие обязательных Python-пакетов. При отсутствии — выход с кодом 1."""
    missing = []
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    try:
        import whisperx  # noqa: F401
    except ImportError:
        missing.append("whisperx")
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp")
    if missing:
        logging.error(
            "Отсутствуют зависимости: %s. Установите: pip install -r requirements.txt",
            ", ".join(missing),
        )
        sys.exit(1)


def check_dependencies():
    """
    Проверяет наличие ffmpeg в PATH и импортирует зависимости.
    Определяет устройство (CUDA/CPU) и compute_type.
    Возвращает: (success: bool, device: str, compute_type: str).
    """
    _check_imports()

    if not shutil.which("ffmpeg"):
        logging.error(
            "FFmpeg не найден в PATH. Установите FFmpeg и добавьте его в PATH."
        )
        sys.exit(1)

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    logging.info("Проверка зависимостей: OK (ffmpeg, torch, whisperx, yt-dlp)")
    logging.info("Устройство: %s, compute_type: %s", device, compute_type)
    return True, device, compute_type


# -----------------------------------------------------------------------------
# Скачивание видео (yt-dlp)
# -----------------------------------------------------------------------------


def download_video(
    url: str,
    output_dir: str,
    *,
    cookies_file: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    """
    Скачивает видео по URL во временную директорию (в output_dir).
    Возвращает абсолютный путь к скачанному файлу.
    При ошибке (невалидная ссылка, сеть) логирует и пробрасывает исключение.
    cookies_file: путь к файлу cookies (Netscape или JSON).
    cookies_from_browser: браузер для извлечения cookies, например 'chrome', 'firefox', 'edge'.
    """
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)
    # Имя по id и расширению, чтобы не перезаписывать и предсказуемо получить путь
    outtmpl = os.path.join(output_dir, "temp_%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        # Полное видео (видео + аудио), затем транскрипция локально на компе
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        # Устойчивость к обрывам соединения (YouTube иногда рвёт подключение)
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
    }
    if cookies_file:
        if not os.path.isfile(cookies_file):
            raise FileNotFoundError(f"Файл cookies не найден: {cookies_file}")
        ydl_opts["cookiefile"] = os.path.abspath(cookies_file)
        logging.info("Используются cookies из файла: %s", cookies_file)
    elif cookies_from_browser:
        browser = cookies_from_browser.strip().lower()
        # Яндекс.Браузер не поддерживается yt-dlp — подсказываем использовать --cookies
        if browser in ("yandex", "yandex browser", "яндекс"):
            raise ValueError(
                "Яндекс.Браузер не поддерживается для --cookies-from-browser. "
                "Экспортируйте cookies вручную и используйте --cookies FILE. "
                "Как: откройте youtube.com в Яндексе → установите расширение «Get cookies.txt» (или аналог) → экспорт в .txt → "
                "python transcribe_video.py URL --cookies путь/к/cookies.txt"
            )
        ydl_opts["cookiesfrombrowser"] = (browser,)
        logging.info("Используются cookies из браузера: %s", cookies_from_browser)
    max_attempts = 3
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logging.info("Скачивание: %s (попытка %d/%d)", url, attempt, max_attempts)
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise RuntimeError("yt-dlp не смог извлечь информацию по ссылке")
                video_path = ydl.prepare_filename(info)
                if not os.path.isfile(video_path):
                    # при merge итоговый файл может иметь другое расширение
                    base = os.path.splitext(video_path)[0]
                    for ext in (".m4a", ".webm", ".opus", ".mp4", ".mkv"):
                        candidate = base + ext
                        if os.path.isfile(candidate):
                            video_path = candidate
                            break
                if not os.path.isfile(video_path):
                    raise FileNotFoundError(
                        "После скачивания файл не найден: " + video_path
                    )
                logging.info("Скачано: %s", video_path)
                return os.path.abspath(video_path)
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_connection_error = (
                "connection" in err_str
                or "10054" in err_str
                or "разорвал" in err_str
                or "transport" in err_str
            )
            if attempt < max_attempts and is_connection_error:
                wait_sec = 5 * attempt
                logging.warning(
                    "Обрыв соединения (попытка %d/%d). Повтор через %d с...",
                    attempt, max_attempts, wait_sec,
                )
                time.sleep(wait_sec)
                continue
            # Подсказка при ошибке доступа к cookies браузера (Edge/Chrome открыт)
            if (
                "cookie" in err_str
                and ("copy" in err_str or "permission" in err_str or "7271" in err_str or "denied" in err_str)
            ):
                logging.error(
                    "Не удалось прочитать cookies: браузер держит файл открытым. "
                    "Вариант 1 — закройте Edge полностью (в т.ч. в диспетчере задач) и запустите снова с --cookies-from-browser edge. "
                    "Вариант 2 — экспортируйте cookies в файл (расширение «Get cookies.txt LOCALLY» в Edge), сохраните как cookies.txt, затем: --cookies путь/к/cookies.txt"
                )
            logging.exception("Ошибка скачивания: %s", e)
            raise last_error


# -----------------------------------------------------------------------------
# Извлечение аудио (ffmpeg) — 16 kHz mono WAV
# -----------------------------------------------------------------------------


def extract_audio_16k_mono(video_path: str, output_dir: str) -> str:
    """
    Извлекает аудио из видео и конвертирует в 16 kHz mono WAV.
    Возвращает путь к созданному .wav файлу.
    """
    base = Path(video_path).stem
    wav_path = os.path.join(output_dir, f"{base}_audio.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-vn",
        wav_path,
    ]
    logging.info("Извлечение аудио: %s -> %s", video_path, wav_path)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        logging.error("ffmpeg stderr: %s", result.stderr)
        raise RuntimeError(
            f"ffmpeg завершился с кодом {result.returncode}: {result.stderr}"
        )
    if not os.path.isfile(wav_path):
        raise FileNotFoundError("ffmpeg не создал файл: " + wav_path)
    logging.info("Аудио готово: %s", wav_path)
    return os.path.abspath(wav_path)


# -----------------------------------------------------------------------------
# Транскрипция и выравнивание (WhisperX)
# -----------------------------------------------------------------------------


def transcribe_and_align(
    wav_path: str,
    device: str,
    compute_type: str,
    model_dir: str | None = None,
    language: str | None = None,
    batch_size: int = 16,
) -> dict:
    """
    Загружает Whisper large-v3, транскрибирует аудио и выполняет word-level alignment.
    Возвращает результат с полями segments (каждый segment содержит words: [{word, start, end}]).
    """
    import whisperx
    from whisperx.utils import get_writer

    # Уменьшаем batch_size для экономии видеопамяти (CUDA) и RAM (CPU)
    if device == "cpu":
        batch_size = min(batch_size, 8)
    else:
        # На GPU large-v3 легко вызывает OOM при batch_size=16 на картах 6–8 GB
        batch_size = min(batch_size, 8)

    logging.info("Загрузка модели Whisper large-v3 (batch_size=%d)...", batch_size)
    model = whisperx.load_model(
        "large-v3",
        device,
        compute_type=compute_type,
        download_root=model_dir,
        language=language,
    )
    audio = whisperx.load_audio(wav_path)
    logging.info("Транскрипция...")
    result = model.transcribe(audio, batch_size=batch_size)
    # Выгружаем модель для экономии памяти перед alignment
    del model
    gc.collect()
    if device == "cuda":
        import torch
        torch.cuda.empty_cache()

    language = result.get("language") or "en"
    segments = result.get("segments") or []
    if not segments:
        logging.warning("Сегменты пусты, выравнивание пропущено.")
        return result

    logging.info("Загрузка модели выравнивания для языка: %s", language)
    align_model = None
    align_metadata = None
    try:
        align_model, align_metadata = whisperx.load_align_model(
            language_code=language,
            device=device,
            model_dir=model_dir,
        )
    except (ValueError, Exception) as e:
        logging.warning("Модель выравнивания для %s недоступна: %s", language, e)
    if align_model is not None and align_metadata is not None:
        logging.info("Выравнивание по словам...")
        result = whisperx.align(
            result["segments"],
            align_model,
            align_metadata,
            wav_path,
            device,
        )
        result["language"] = language
        del align_model
    else:
        logging.warning("Модель выравнивания не загружена, word-level таймкоды недоступны.")

    gc.collect()
    if device == "cuda":
        import torch
        torch.cuda.empty_cache()

    return result


# -----------------------------------------------------------------------------
# Сохранение выходных файлов
# -----------------------------------------------------------------------------


def save_outputs(
    result: dict,
    base_name: str,
    output_dir: str,
    audio_path: str,
) -> tuple[str, str, str]:
    """
    Сохраняет полный текст (.txt), JSON со словами и таймкодами (.json), субтитры (.srt).
    Возвращает кортеж (path_txt, path_json, path_srt).
    """
    from whisperx.utils import get_writer

    os.makedirs(output_dir, exist_ok=True)

    # Writer принимает (result, audio_path, options)
    writer_options = {
        "highlight_words": False,
        "max_line_count": None,
        "max_line_width": None,
    }

    # .txt
    writer_txt = get_writer("txt", output_dir)
    writer_txt(result, audio_path, writer_options)
    txt_path = os.path.join(output_dir, base_name + ".txt")
    # get_writer пишет по имени audio_path; переименуем при необходимости
    actual_txt = os.path.join(output_dir, Path(audio_path).stem + ".txt")
    if actual_txt != txt_path and os.path.isfile(actual_txt):
        os.rename(actual_txt, txt_path)
    else:
        txt_path = actual_txt

    # .srt
    writer_srt = get_writer("srt", output_dir)
    writer_srt(result, audio_path, writer_options)
    srt_path = os.path.join(output_dir, Path(audio_path).stem + ".srt")
    target_srt = os.path.join(output_dir, base_name + ".srt")
    if srt_path != target_srt and os.path.isfile(srt_path):
        os.rename(srt_path, target_srt)
    else:
        target_srt = srt_path
    srt_path = target_srt

    # JSON: список { "word", "start", "end" }
    words_list = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words_list.append({
                "word": w.get("word", "").strip(),
                "start": round(w.get("start", 0.0), 3),
                "end": round(w.get("end", 0.0), 3),
            })
    json_path = os.path.join(output_dir, base_name + "_words.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(words_list, f, ensure_ascii=False, indent=2)

    logging.info("Сохранено: %s, %s, %s", txt_path, json_path, srt_path)
    return txt_path, json_path, srt_path


# -----------------------------------------------------------------------------
# Готовые субтитры YouTube/др. — текст без транскрипции
# -----------------------------------------------------------------------------


def try_fetch_subs(
    url: str,
    output_dir: str,
    *,
    cookies_file: str | None = None,
    cookies_from_browser: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Пытается скачать только субтитры (без видео) через yt-dlp.
    Возвращает (путь к .srt файлу, base_name) или (None, None), если субтитров нет.
    """
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "subs_%(id)s.%(ext)s")
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "srt/best",
        "subtitleslangs": ["en", "ru", "en-US", "ru-RU", "a.en", "a.ru"],
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
    }
    if cookies_file and os.path.isfile(cookies_file):
        ydl_opts["cookiefile"] = os.path.abspath(cookies_file)
    elif cookies_from_browser:
        browser = cookies_from_browser.strip().lower()
        if browser not in ("yandex", "yandex browser", "яндекс"):
            ydl_opts["cookiesfrombrowser"] = (browser,)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            return None, None
        video_id = info.get("id") or "unknown"
        base_name = video_id
        # Ищем скачанный .srt (yt-dlp может записать как subs_VIDEOID.en.srt и т.д.)
        for f in os.listdir(output_dir):
            if f.startswith("subs_") and (f.endswith(".srt") or f.endswith(".vtt")):
                path = os.path.join(output_dir, f)
                if f.endswith(".vtt"):
                    # конвертируем vtt -> srt простым переименованием не получится; оставляем как есть и парсим vtt
                    return path, base_name
                return path, base_name
        return None, None
    except Exception as e:
        logging.debug("Субтитры недоступны (%s): %s", url, e)
        return None, None


def _parse_srt(content: str) -> list[tuple[float, float, str]]:
    """Парсит содержимое SRT, возвращает список (start_sec, end_sec, text)."""
    import re
    segments = []
    # Блоки разделены пустой строкой; каждый блок: номер, таймкод, текст
    blocks = re.split(r"\n\s*\n", content.strip())
    time_line = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d+)"
    )
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        match = time_line.search(lines[1])
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
        text = " ".join(lines[2:]).replace("\n", " ").strip()
        if text:
            segments.append((start, end, text))
    return segments


def _parse_vtt(content: str) -> list[tuple[float, float, str]]:
    """Парсит WebVTT, возвращает список (start_sec, end_sec, text)."""
    import re
    content = re.sub(r"^WEBVTT\s*\n?", "", content)
    # Время в VTT с точкой; _parse_srt принимает и , и . в regex
    return _parse_srt(content)


def subs_to_outputs(
    subs_path: str, base_name: str, output_dir: str
) -> tuple[str, str, str]:
    """
    По файлу субтитров (.srt или .vtt) создаёт .txt, .json (сегменты), .srt.
    Возвращает (txt_path, json_path, srt_path).
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(subs_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    if subs_path.lower().endswith(".vtt"):
        segments = _parse_vtt(raw)
    else:
        segments = _parse_srt(raw)
    if not segments:
        raise ValueError("В файле субтитров нет данных")
    # .txt — весь текст
    full_text = "\n".join(text for _, _, text in segments)
    txt_path = os.path.join(output_dir, base_name + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    # .json — сегменты с таймкодами (как у WhisperX, но без word-level)
    words_list = [
        {"start": round(s, 3), "end": round(e, 3), "word": t}
        for s, e, t in segments
    ]
    json_path = os.path.join(output_dir, base_name + "_words.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(words_list, f, ensure_ascii=False, indent=2)
    # .srt — копируем/переименовываем в стандартное имя
    srt_path = os.path.join(output_dir, base_name + ".srt")
    if os.path.abspath(subs_path) != os.path.abspath(srt_path):
        shutil.copy2(subs_path, srt_path)
    logging.info("Сохранено из субтитров: %s, %s, %s", txt_path, json_path, srt_path)
    return txt_path, json_path, srt_path


# -----------------------------------------------------------------------------
# Очистка временных файлов
# -----------------------------------------------------------------------------


def cleanup(paths: list[str]) -> None:
    """Удаляет переданные файлы. Игнорирует отсутствующие файлы и ошибки."""
    for p in paths:
        if not p:
            continue
        try:
            if os.path.isfile(p):
                os.remove(p)
                logging.info("Удалён: %s", p)
        except OSError as e:
            logging.warning("Не удалось удалить %s: %s", p, e)


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Транскрипция видео: скачивание -> аудио 16kHz -> Whisper large-v3 -> WhisperX alignment -> .txt, .json, .srt",
    )
    parser.add_argument(
        "url",
        type=str,
        help="Ссылка на видео (YouTube, Instagram, TikTok, прямая mp4 и т.д.)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Директория для выходных файлов и временных (по умолчанию: output)",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Директория кэша моделей Whisper/WhisperX (по умолчанию: стандартный кэш)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Код языка (например en, ru). По умолчанию — автоопределение.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Не удалять скачанное видео и временный WAV после успеха",
    )
    parser.add_argument(
        "--cookies",
        type=str,
        default=None,
        metavar="FILE",
        help="Путь к файлу cookies (Netscape или JSON) для YouTube и др. См. https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp",
    )
    parser.add_argument(
        "--cookies-from-browser",
        type=str,
        default=None,
        metavar="BROWSER",
        help="Cookies из браузера: chrome, firefox, edge, opera, brave, vivaldi (Яндекс не поддерживается — используйте --cookies с экспортом)",
    )
    parser.add_argument(
        "--force-transcribe",
        action="store_true",
        help="Всегда использовать Whisper (не пытаться взять готовые субтитры YouTube)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробный вывод (DEBUG)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        metavar="N",
        help="Размер батча для Whisper (меньше = меньше видеопамяти, дольше работа). По умолчанию 8; при CUDA out of memory попробуйте 4 или 2.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    success, device, compute_type = check_dependencies()
    if not success:
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    temp_dir = output_dir
    video_path = None
    wav_path = None

    try:
        # Сначала пробуем взять готовые субтитры YouTube — текст без загрузки и без Whisper
        if not args.force_transcribe:
            subs_path, base_name = try_fetch_subs(
                args.url,
                temp_dir,
                cookies_file=args.cookies,
                cookies_from_browser=args.cookies_from_browser,
            )
            if subs_path and base_name:
                try:
                    txt_path, json_path, srt_path = subs_to_outputs(
                        subs_path, base_name, output_dir
                    )
                    logging.info("Найдены готовые субтитры, сохраняю текст без транскрипции")
                    cleanup([subs_path])
                    print("\nГотово (из субтитров, без распознавания речи):")
                    print("  TXT:", txt_path)
                    print("  JSON:", json_path)
                    print("  SRT:", srt_path)
                    return
                except ValueError as e:
                    if "нет данных" in str(e):
                        logging.warning(
                            "Файл субтитров пустой или в неподдерживаемом формате — скачиваю видео и транскрибирую"
                        )
                        cleanup([subs_path])
                    else:
                        raise
            if not (subs_path and base_name):
                logging.info("Готовых субтитров нет — скачиваю видео и транскрибирую")

        video_path = download_video(
            args.url,
            temp_dir,
            cookies_file=args.cookies,
            cookies_from_browser=args.cookies_from_browser,
        )
        wav_path = extract_audio_16k_mono(video_path, temp_dir)
        base_name = Path(wav_path).stem.replace("_audio", "")
        result = transcribe_and_align(
            wav_path,
            device=device,
            compute_type=compute_type,
            model_dir=args.model_dir,
            language=args.language,
            batch_size=args.batch_size,
        )
        txt_path, json_path, srt_path = save_outputs(
            result, base_name, output_dir, wav_path
        )

        if not args.keep_temp:
            to_remove = [video_path, wav_path]
            cleanup(to_remove)

        print("\nГотово. Созданные файлы:")
        print("  TXT:", txt_path)
        print("  JSON:", json_path)
        print("  SRT:", srt_path)

    except Exception as e:
        logging.exception("Ошибка: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()


"""текст"""