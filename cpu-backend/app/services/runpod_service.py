from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

RUNPOD_API_BASE = "https://api.runpod.io/graphql"


async def start_pod() -> str | None:
    """Start RunPod On-Demand pod. Returns pod_id or None on failure."""
    if not settings.RUNPOD_API_KEY or not settings.RUNPOD_POD_TEMPLATE_ID:
        log.warning("RunPod credentials not configured")
        return None

    mutation = """
    mutation {
      podFindAndDeployOnDemand(input: {
        cloudType: SECURE,
        gpuCount: 1,
        volumeInGb: 50,
        containerDiskInGb: 20,
        minVcpuCount: 4,
        minMemoryInGb: 16,
        gpuTypeId: "%s",
        name: "clips-gpu-worker",
        templateId: "%s",
        startJupyter: false,
        startSsh: true
      }) {
        id
        desiredStatus
      }
    }
    """ % (settings.RUNPOD_GPU_TYPE, settings.RUNPOD_POD_TEMPLATE_ID)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            RUNPOD_API_BASE,
            json={"query": mutation},
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
        )
    if resp.status_code != 200:
        log.error("RunPod start pod failed: %s", resp.text[:300])
        return None
    data = resp.json()
    pod_id = (data.get("data", {}).get("podFindAndDeployOnDemand", {}) or {}).get("id")
    log.info("RunPod pod started: %s", pod_id)
    return pod_id


async def get_pod_status(pod_id: str) -> str:
    """Returns pod status string: RUNNING, EXITED, etc."""
    query = """
    query {
      pod(input: {podId: "%s"}) {
        id
        desiredStatus
        runtime { status }
      }
    }
    """ % pod_id

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            RUNPOD_API_BASE,
            json={"query": query},
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
        )
    if resp.status_code != 200:
        return "UNKNOWN"
    data = resp.json()
    pod = (data.get("data", {}).get("pod")) or {}
    runtime = pod.get("runtime") or {}
    return runtime.get("status") or pod.get("desiredStatus") or "UNKNOWN"


async def stop_pod(pod_id: str) -> bool:
    """Stop/terminate a RunPod pod."""
    mutation = """
    mutation {
      podTerminate(input: {podId: "%s"})
    }
    """ % pod_id

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            RUNPOD_API_BASE,
            json={"query": mutation},
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
        )
    ok = resp.status_code == 200
    log.info("RunPod stop pod %s: %s", pod_id, "OK" if ok else resp.text[:200])
    return ok


async def wait_for_pod_ready(pod_id: str) -> bool:
    """
    Poll pod status until RUNNING or timeout.
    Returns True if pod became RUNNING within timeout.
    """
    timeout = settings.RUNPOD_POD_START_TIMEOUT_SEC
    interval = settings.RUNPOD_POD_POLL_INTERVAL_SEC
    elapsed = 0
    while elapsed < timeout:
        status = await get_pod_status(pod_id)
        log.info("Pod %s status: %s (elapsed %ds)", pod_id, status, elapsed)
        if status in ("RUNNING", "running"):
            return True
        if status in ("EXITED", "DEAD", "FAILED"):
            return False
        await asyncio.sleep(interval)
        elapsed += interval
    return False
