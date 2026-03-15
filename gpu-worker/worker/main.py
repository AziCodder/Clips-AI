from __future__ import annotations

"""
GPU Worker main loop.
- Polls CPU API for next transcription job
- Downloads audio from S3
- Runs WhisperX transcribe + align
- Uploads results to S3
- Reports to CPU (completed/failed)
- After ACK: deletes local files
- Shuts down after IDLE_SHUTDOWN_SEC seconds with no jobs
- Hard-kills (sys.exit) if a single job exceeds JOB_MAX_DURATION_SEC
"""

import logging
import os
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

from worker.config import settings
from worker import cpu_client, s3_client
from worker.io_layout import (
    audio_path,
    job_dir,
    s3_prefix,
    s3_segments_json,
    s3_subtitles_srt,
    s3_transcript_txt,
    s3_words_json,
    segments_json,
    subtitles_srt,
    transcript_txt,
    words_json,
)
from worker.transcriber_whisperx import save_outputs, transcribe_and_align

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def process_job(job: dict) -> None:
    job_id = str(job["job_id"])
    video_id = str(job["video_id"])
    s3_audio_key = job["s3_audio_key"]
    language_hint = job.get("language_hint")

    out_dir = job_dir(job_id)
    os.makedirs(out_dir, exist_ok=True)
    local_audio = audio_path(job_id, "flac")

    try:
        log.info("=== Job %s: start ===", job_id)
        cpu_client.mark_started(job_id)

        # Download audio from S3
        log.info("Downloading audio %s -> %s", s3_audio_key, local_audio)
        s3_client.download(s3_audio_key, local_audio)

        # Check if cancelled before heavy GPU work
        if cpu_client.check_cancelled(job_id):
            log.info("Job %s was cancelled, stopping", job_id)
            return

        t0 = time.time()
        result = transcribe_and_align(local_audio, out_dir, language=language_hint)
        elapsed = time.time() - t0
        detected_lang = result.get("language")
        log.info("Transcription done in %.1fs, language=%s", elapsed, detected_lang)

        save_outputs(result, out_dir, job_id, local_audio)

        # Upload all artifacts to S3
        prefix = s3_prefix(video_id, job_id)
        _upload_artifacts(out_dir, video_id, job_id)
        log.info("Uploaded artifacts to S3 prefix %s", prefix)

        # Report completed to CPU
        ack_data = cpu_client.mark_completed(
            job_id,
            s3_prefix=prefix,
            duration_sec=elapsed,
            language=detected_lang,
        )
        ack = ack_data.get("ack", False) if isinstance(ack_data, dict) else False
        if not ack:
            log.error("CPU did not ACK job %s: %s", job_id, ack_data)
            return

        log.info("Job %s: ACK received, cleaning up local files", job_id)

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("Job %s failed: %s\n%s", job_id, exc, tb)
        cpu_client.mark_failed(job_id, type(exc).__name__, tb, retryable=True)

    finally:
        # Clean up local job directory after ACK or failure
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)
            log.info("Cleaned up local dir %s", out_dir)
        cpu_client.mark_cleanup_done(job_id)


def _upload_artifacts(out_dir: str, video_id: str, job_id: str) -> None:
    uploads = [
        (os.path.join(out_dir, "transcript.txt"), s3_transcript_txt(video_id, job_id), "text/plain"),
        (os.path.join(out_dir, "words.json"), s3_words_json(video_id, job_id), "application/json"),
        (os.path.join(out_dir, "segments.json"), s3_segments_json(video_id, job_id), "application/json"),
        (os.path.join(out_dir, "subtitles.srt"), s3_subtitles_srt(video_id, job_id), "text/plain"),
    ]
    for local_path, s3_key, content_type in uploads:
        if os.path.isfile(local_path):
            s3_client.upload(local_path, s3_key, content_type)
        else:
            log.warning("Artifact not found: %s", local_path)


def _run_job_in_thread(job: dict, done_event: threading.Event) -> None:
    """Wrapper that signals done_event regardless of success/failure."""
    try:
        process_job(job)
    finally:
        done_event.set()


def main() -> None:
    os.makedirs(settings.WORK_DIR, exist_ok=True)
    log.info(
        "GPU Worker %s starting. IDLE shutdown after %ds, job timeout after %ds",
        settings.WORKER_ID,
        settings.IDLE_SHUTDOWN_SEC,
        settings.JOB_MAX_DURATION_SEC,
    )
    from worker.health import start_health_server
    start_health_server(port=8080)
    log.info("Health endpoint: http://0.0.0.0:8080/health")

    idle_since = time.time()

    while True:
        job = cpu_client.get_next_job()
        if job is None:
            idle_sec = time.time() - idle_since
            if idle_sec >= settings.IDLE_SHUTDOWN_SEC:
                log.info("No jobs for %ds, shutting down", settings.IDLE_SHUTDOWN_SEC)
                sys.exit(0)
            time.sleep(settings.POLL_INTERVAL_SEC)
            continue

        idle_since = time.time()  # reset idle timer when job found
        job_id = str(job.get("job_id", "unknown"))

        done_event = threading.Event()
        t = threading.Thread(
            target=_run_job_in_thread,
            args=(job, done_event),
            daemon=True,
        )
        t.start()

        finished_in_time = done_event.wait(timeout=settings.JOB_MAX_DURATION_SEC)

        if not finished_in_time:
            log.error(
                "Job %s exceeded max duration %ds — reporting timeout to CPU and exiting",
                job_id,
                settings.JOB_MAX_DURATION_SEC,
            )
            try:
                cpu_client.mark_timeout(job_id)
            except Exception as exc:
                log.error("Failed to report timeout for job %s: %s", job_id, exc)
            # Exit so the instance dies; CPU will restart GPU when admin retries the job
            sys.exit(1)


if __name__ == "__main__":
    main()
