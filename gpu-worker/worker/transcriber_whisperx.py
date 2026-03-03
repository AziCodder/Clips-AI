from __future__ import annotations

"""
WhisperX transcription and alignment — adapted from transcribe_video.py.
GPU-only, runs one job at a time.
"""

import gc
import json
import logging
import os
from pathlib import Path

from worker.config import settings
from worker.io_layout import (
    audio_path,
    job_dir,
    meta_json,
    segments_json,
    subtitles_srt,
    transcript_txt,
    words_json,
)

log = logging.getLogger(__name__)


def transcribe_and_align(
    wav_path: str,
    out_dir: str,
    language: str | None = None,
) -> dict:
    """
    Run WhisperX large-v3 + alignment.
    Returns result dict with segments and language.
    Mirrors transcribe_video.py::transcribe_and_align but uses worker config.
    """
    import whisperx
    from whisperx.utils import get_writer

    device = settings.WHISPER_DEVICE
    compute_type = settings.WHISPER_COMPUTE_TYPE
    batch_size = settings.WHISPER_BATCH_SIZE
    model_dir = settings.WHISPER_MODEL_DIR or None

    if device == "cpu":
        batch_size = min(batch_size, 4)

    log.info("Loading WhisperX large-v3 (device=%s, batch_size=%d)...", device, batch_size)
    model = whisperx.load_model(
        settings.WHISPER_MODEL,
        device,
        compute_type=compute_type,
        download_root=model_dir,
        language=language,
    )
    audio = whisperx.load_audio(wav_path)
    log.info("Transcribing...")
    result = model.transcribe(audio, batch_size=batch_size)

    del model
    gc.collect()
    if device == "cuda":
        import torch
        torch.cuda.empty_cache()

    detected_lang = result.get("language") or "en"
    segments = result.get("segments") or []

    if segments:
        log.info("Aligning (language=%s)...", detected_lang)
        align_model = None
        align_metadata = None
        try:
            align_model, align_metadata = whisperx.load_align_model(
                language_code=detected_lang,
                device=device,
                model_dir=model_dir,
            )
        except Exception as exc:
            log.warning("Alignment model not available for %s: %s", detected_lang, exc)

        if align_model is not None:
            result = whisperx.align(
                result["segments"],
                align_model,
                align_metadata,
                wav_path,
                device,
            )
            result["language"] = detected_lang
            del align_model

        gc.collect()
        if device == "cuda":
            import torch
            torch.cuda.empty_cache()

    return result


def save_outputs(result: dict, out_dir: str, job_id: str, wav_path: str) -> None:
    """
    Save WhisperX result to out_dir:
      transcript.txt, words.json, segments.json, subtitles.srt, meta.json
    """
    from whisperx.utils import get_writer

    os.makedirs(out_dir, exist_ok=True)

    writer_opts = {"highlight_words": False, "max_line_count": None, "max_line_width": None}

    # .txt
    writer_txt = get_writer("txt", out_dir)
    writer_txt(result, wav_path, writer_opts)
    # rename to standard name
    actual_txt = os.path.join(out_dir, Path(wav_path).stem + ".txt")
    target_txt = os.path.join(out_dir, "transcript.txt")
    if os.path.isfile(actual_txt) and actual_txt != target_txt:
        os.rename(actual_txt, target_txt)

    # .srt
    writer_srt = get_writer("srt", out_dir)
    writer_srt(result, wav_path, writer_opts)
    actual_srt = os.path.join(out_dir, Path(wav_path).stem + ".srt")
    target_srt = os.path.join(out_dir, "subtitles.srt")
    if os.path.isfile(actual_srt) and actual_srt != target_srt:
        os.rename(actual_srt, target_srt)

    # words.json
    words_list = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words_list.append({
                "word": w.get("word", "").strip(),
                "start": round(w.get("start", 0.0), 3),
                "end": round(w.get("end", 0.0), 3),
            })
    with open(os.path.join(out_dir, "words.json"), "w", encoding="utf-8") as f:
        json.dump(words_list, f, ensure_ascii=False, indent=2)

    # segments.json
    segments_list = [
        {
            "start": round(s.get("start", 0.0), 3),
            "end": round(s.get("end", 0.0), 3),
            "text": s.get("text", "").strip(),
        }
        for s in result.get("segments", [])
    ]
    with open(os.path.join(out_dir, "segments.json"), "w", encoding="utf-8") as f:
        json.dump(segments_list, f, ensure_ascii=False, indent=2)

    # meta.json
    meta = {
        "language": result.get("language"),
        "segment_count": len(segments_list),
        "word_count": len(words_list),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log.info("Outputs saved to %s", out_dir)
