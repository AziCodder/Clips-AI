from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from worker.config import settings

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {settings.GPU_API_KEY}",
    "Content-Type": "application/json",
}


def _url(path: str) -> str:
    return f"{settings.CPU_API_BASE_URL}{path}"


def get_next_job() -> dict[str, Any] | None:
    """Poll CPU for next job. Returns job dict or None."""
    with httpx.Client(timeout=30, verify=True) as client:
        resp = client.get(_url("/gpu/jobs/next"), headers=_HEADERS)
    if resp.status_code == 200:
        return resp.json()
    log.warning("get_next_job: %s %s", resp.status_code, resp.text[:200])
    return None


def mark_started(job_id: str) -> None:
    with httpx.Client(timeout=30, verify=True) as client:
        resp = client.post(
            _url(f"/gpu/jobs/{job_id}/started"),
            headers=_HEADERS,
            json={"worker_id": settings.WORKER_ID, "started_at": datetime.now(timezone.utc).isoformat()},
        )
    if resp.status_code not in (200, 204):
        log.warning("mark_started failed: %s", resp.text[:200])


def mark_completed(job_id: str, s3_prefix: str, duration_sec: float, language: str | None) -> dict[str, Any]:
    with httpx.Client(timeout=60, verify=True) as client:
        resp = client.post(
            _url(f"/gpu/jobs/{job_id}/completed"),
            headers=_HEADERS,
            json={
                "worker_id": settings.WORKER_ID,
                "s3_prefix_results": s3_prefix,
                "duration_sec": duration_sec,
                "detected_language": language,
                "meta": {},
            },
        )
    if resp.status_code == 200:
        return resp.json()
    log.warning("mark_completed failed: %s", resp.text[:200])
    return {"ack": False, "reason": resp.text[:200]}


def mark_failed(job_id: str, error_type: str, traceback: str, retryable: bool = True) -> None:
    with httpx.Client(timeout=30, verify=True) as client:
        resp = client.post(
            _url(f"/gpu/jobs/{job_id}/failed"),
            headers=_HEADERS,
            json={
                "worker_id": settings.WORKER_ID,
                "error_type": error_type,
                "traceback": traceback,
                "retryable": retryable,
            },
        )
    if resp.status_code not in (200, 204):
        log.warning("mark_failed: %s", resp.text[:200])


def mark_cleanup_done(job_id: str) -> None:
    with httpx.Client(timeout=30, verify=True) as client:
        resp = client.post(_url(f"/gpu/jobs/{job_id}/cleanup-done"), headers=_HEADERS)
    if resp.status_code not in (200, 204):
        log.warning("mark_cleanup_done: %s", resp.text[:200])


def check_cancelled(job_id: str) -> bool:
    """Check if job was cancelled or timed-out by CPU."""
    with httpx.Client(timeout=15, verify=True) as client:
        resp = client.get(_url(f"/gpu/jobs/{job_id}/ack"), headers=_HEADERS)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("reason") in ("cancelled", "timed_out")
    return False


def mark_timeout(job_id: str) -> None:
    """Notify CPU that this job exceeded the maximum allowed duration."""
    with httpx.Client(timeout=20, verify=True) as client:
        resp = client.post(_url(f"/gpu/jobs/{job_id}/timeout"), headers=_HEADERS)
    if resp.status_code not in (200, 204):
        log.warning("mark_timeout: %s %s", resp.status_code, resp.text[:200])
