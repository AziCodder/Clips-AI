"""Vast.ai API client: search offers, create instance, poll status, destroy."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

VASTAI_API_BASE = "https://console.vast.ai/api/v0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.VASTAI_API_KEY}"}


async def start_instance() -> int | None:
    """
    Search for a GPU offer and create a Vast.ai instance.
    Returns instance_id (new_contract) or None on failure.
    """
    if not settings.VASTAI_API_KEY:
        log.warning("Vast.ai API key not configured")
        return None

    # 1) Search offers
    search_body: dict[str, Any] = {
        "limit": 20,
        "type": "ondemand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"eq": 1},
    }
    if settings.VASTAI_GPU_NAME:
        search_body["gpu_name"] = {"eq": settings.VASTAI_GPU_NAME}
    if settings.VASTAI_RELIABILITY_MIN is not None:
        search_body["reliability"] = {"gte": settings.VASTAI_RELIABILITY_MIN}
    if settings.VASTAI_DPH_MAX is not None:
        search_body["dph_total"] = {"lte": settings.VASTAI_DPH_MAX}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{VASTAI_API_BASE}/bundles/",
            json=search_body,
            headers=_headers(),
        )
    if resp.status_code != 200:
        log.error("Vast.ai search offers failed: %s", resp.text[:300])
        return None

    data = resp.json()
    offers = data.get("offers") or []
    if not offers:
        log.error("Vast.ai: no offers found for criteria")
        return None

    # Use first offer (optionally sort by dph_total; API may return sorted)
    offer = offers[0]
    offer_id = offer.get("id")
    if offer_id is None:
        log.error("Vast.ai: offer has no id: %s", offer)
        return None

    # 2) Create instance from offer
    base_url = (settings.TELEGRAM_WEBHOOK_BASE_URL or "").strip().rstrip("/")
    api_base = f"{base_url}/api/v1" if base_url else ""
    create_body: dict[str, Any] = {
        "image": settings.VASTAI_IMAGE,
        "disk": settings.VASTAI_DISK_GB,
        "runtype": "ssh",
        "target_state": "running",
        "extra_env": {
            "CPU_API_BASE_URL": api_base or "https://your-domain.com/api/v1",
            "GPU_API_KEY": settings.GPU_API_KEY,
            "S3_ENDPOINT_URL": settings.S3_ENDPOINT_URL,
            "S3_ACCESS_KEY": settings.S3_ACCESS_KEY,
            "S3_SECRET_KEY": settings.S3_SECRET_KEY,
            "S3_BUCKET": settings.S3_BUCKET,
        },
    }
    if settings.VASTAI_ONSTART:
        create_body["onstart"] = settings.VASTAI_ONSTART

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.put(
            f"{VASTAI_API_BASE}/asks/{offer_id}/",
            json=create_body,
            headers=_headers(),
        )
    if resp.status_code != 200:
        log.error("Vast.ai create instance failed: %s", resp.text[:300])
        return None

    result = resp.json()
    instance_id = result.get("new_contract")
    if instance_id is None:
        log.error("Vast.ai create response missing new_contract: %s", result)
        return None

    log.info("Vast.ai instance created: %s", instance_id)
    return int(instance_id)


async def get_instance_status(instance_id: int) -> str:
    """Returns instance status string: CONNECT, CREATING, LOADING, etc."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{VASTAI_API_BASE}/instances/{instance_id}/",
            headers=_headers(),
        )
    if resp.status_code != 200:
        log.warning("Vast.ai get instance %s: %s %s", instance_id, resp.status_code, resp.text[:200])
        return "UNKNOWN"
    data = resp.json()
    return (data.get("status") or data.get("actual_status") or "UNKNOWN").upper()


async def destroy_instance(instance_id: int) -> bool:
    """Destroy a Vast.ai instance."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{VASTAI_API_BASE}/instances/{instance_id}/",
            headers=_headers(),
        )
    ok = resp.status_code == 200
    log.info("Vast.ai destroy instance %s: %s", instance_id, "OK" if ok else resp.text[:200])
    return ok


async def wait_for_instance_ready(instance_id: int) -> bool:
    """
    Poll instance status until CONNECT (SSH ready) or timeout.
    Returns True if instance became ready within timeout.
    """
    timeout = settings.VASTAI_INSTANCE_START_TIMEOUT_SEC
    interval = settings.VASTAI_POLL_INTERVAL_SEC
    elapsed = 0
    ready_statuses = ("CONNECT", "OPEN")
    terminal_bad = ("INACTIVE", "OFFLINE", "FAILED", "EXITED", "CANCELLED")

    while elapsed < timeout:
        status = await get_instance_status(instance_id)
        log.info("Vast.ai instance %s status: %s (elapsed %ds)", instance_id, status, elapsed)
        if status in ready_statuses:
            return True
        if status in terminal_bad:
            return False
        await asyncio.sleep(interval)
        elapsed += interval
    return False
