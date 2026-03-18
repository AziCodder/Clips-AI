"""Vast.ai API client: search offers, create instance, poll status, destroy."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

VASTAI_API_BASE = "https://console.vast.ai/api/v0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.VASTAI_API_KEY}"}


def _build_onstart_command() -> str:
    """
    Build a robust onstart command for fresh Vast.ai instances.

    If user configured a custom command, keep it as-is.
    If legacy value points to a local file path that may not exist on a clean
    instance, replace it with a bootstrap command that clones the repo first.
    """
    raw = (settings.VASTAI_ONSTART or "").strip()
    legacy_values = {
        "bash /root/clips/infra/vastai-onstart.sh",
        "/bin/bash /root/clips/infra/vastai-onstart.sh",
    }
    if raw and raw not in legacy_values:
        return raw

    if raw in legacy_values:
        log.warning(
            "VASTAI_ONSTART uses legacy local path; switching to bootstrap command for clean instances"
        )

    # Robust default: ensure repo exists, then run project onstart script.
    # Keep REPO_URL overridable via GIT_REPO_URL env on Vast side.
    return (
        "bash -lc 'set -e; "
        "export PATH=/usr/local/bin:/usr/bin:/bin:$PATH; "
        "REPO_URL=${GIT_REPO_URL:-https://github.com/AziCodder/Clips-AI.git}; "
        "REPO_DIR=/root/clips; "
        "if [ ! -d \"$REPO_DIR/.git\" ]; then rm -rf \"$REPO_DIR\"; git clone \"$REPO_URL\" \"$REPO_DIR\"; fi; "
        "cd \"$REPO_DIR\"; "
        "git pull --ff-only || true; "
        "bash \"$REPO_DIR/infra/vastai-onstart.sh'"
    )


def _instance_status(instance: dict[str, Any]) -> str:
    return str(
        instance.get("actual_status")
        or instance.get("cur_state")
        or instance.get("status")
        or instance.get("intended_status")
        or "UNKNOWN"
    ).upper()


def _tokenize_gpu_name(name: str) -> list[str]:
    # Split mixed tokens like "6000Ada" into ["6000", "ada"].
    return re.findall(r"[a-z]+|\d+", (name or "").lower())


def _gpu_name_matches(instance_gpu_name: str, wanted_gpu_name: str) -> bool:
    if not wanted_gpu_name:
        return True

    inst_tokens = _tokenize_gpu_name(instance_gpu_name)
    want_tokens = _tokenize_gpu_name(wanted_gpu_name)
    if not inst_tokens or not want_tokens:
        return False

    inst_set = set(inst_tokens)
    # Ignore broad marketing suffixes to match names like "RTX 6000 Ada" vs "RTX PRO 6000 S".
    stopwords = {"nvidia", "geforce", "series", "pro", "super", "ti", "s", "ada"}
    wanted_numbers = {t for t in want_tokens if t.isdigit()}
    wanted_words = {t for t in want_tokens if not t.isdigit() and t not in stopwords}

    if wanted_numbers and not wanted_numbers.issubset(inst_set):
        return False
    if wanted_words and not any(word in inst_set for word in wanted_words):
        return False
    return True


def _candidate_rank(status: str) -> int:
    if status in {"CONNECT", "OPEN", "RUNNING"}:
        return 0
    if status in {"CREATING", "LOADING", "STARTING", "SCHEDULED"}:
        return 1
    if status in {"INACTIVE", "STOPPED", "EXITED", "OFFLINE"}:
        return 2
    return 3


def _pick_existing_instance(instances: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred_id = settings.VASTAI_PREFERRED_INSTANCE_ID
    if preferred_id is not None:
        for inst in instances:
            try:
                inst_id = int(inst.get("id"))
            except (TypeError, ValueError):
                continue
            if inst_id == preferred_id:
                return inst
        # Preferred ID not found - pick any by GPU

    filtered = [
        inst
        for inst in instances
        if _gpu_name_matches(str(inst.get("gpu_name") or ""), settings.VASTAI_GPU_NAME)
    ]
    if not filtered:
        return None

    filtered.sort(key=lambda inst: (_candidate_rank(_instance_status(inst)), int(inst.get("id") or 0)))
    return filtered[0]


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _offer_rank(offer: dict[str, Any]) -> tuple[float, float, float]:
    dlperf = _to_float(offer.get("dlperf")) or 0.0
    flops = _to_float(offer.get("total_flops")) or 0.0
    dph = _to_float(offer.get("dph_total")) or 9999.0
    # Higher perf first, lower price as tiebreaker.
    return (-dlperf, -flops, dph)


def _offer_perf(offer: dict[str, Any]) -> float:
    # Prefer dlperf when available; fallback to FLOPS.
    dlperf = _to_float(offer.get("dlperf")) or 0.0
    if dlperf > 0:
        return dlperf
    flops = _to_float(offer.get("total_flops")) or 0.0
    return flops


def _offer_dph(offer: dict[str, Any]) -> float:
    return _to_float(offer.get("dph_total")) or 9999.0


def _offer_vram_gb(offer: dict[str, Any]) -> float:
    # Vast can return vram in MB-ish units in different fields.
    vram_mb = _to_float(offer.get("gpu_totalram"))
    if vram_mb and vram_mb > 0:
        return vram_mb / 1024.0
    vram_gb = _to_float(offer.get("gpu_ram"))
    if vram_gb and vram_gb > 0:
        # If API already returns GB in this field, keep it.
        if vram_gb <= 256:
            return vram_gb
        return vram_gb / 1024.0
    return 0.0


def _offer_value_rank(offer: dict[str, Any]) -> tuple[float, float, float]:
    """
    Lower is better:
    - estimated job cost ~ dph / perf
    - then faster runtime ~ 1 / perf
    - then lower hourly cost
    """
    perf = _offer_perf(offer)
    dph = _offer_dph(offer)
    if perf <= 0:
        return (9999.0, 9999.0, dph)
    est_cost_per_work_unit = dph / perf
    est_time_for_work_unit = 1.0 / perf
    return (est_cost_per_work_unit, est_time_for_work_unit, dph)


def _resolve_selection_profile(profile: str | None) -> Literal["speed", "balanced", "economy"]:
    value = (profile or settings.VASTAI_SELECTION_PROFILE or "balanced").strip().lower()
    if value in {"speed", "balanced", "economy"}:
        return value
    return "balanced"


def _offer_profile_rank(offer: dict[str, Any], profile: Literal["speed", "balanced", "economy"]) -> tuple[float, float, float]:
    perf = _offer_perf(offer)
    dph = _offer_dph(offer)
    if perf <= 0:
        return (9999.0, 9999.0, dph)

    est_cost = dph / perf
    est_time = 1.0 / perf
    if profile == "speed":
        return (est_time, est_cost, dph)
    if profile == "economy":
        return (est_cost, est_time, dph)
    return (0.6 * est_cost + 0.4 * est_time, est_time, dph)


def _select_offers_for_budget(
    offers: list[dict[str, Any]],
    profile: Literal["speed", "balanced", "economy"],
) -> list[dict[str, Any]]:
    dph_min = settings.VASTAI_DPH_MIN
    dph_max = settings.VASTAI_DPH_MAX
    vram_min = settings.VASTAI_MIN_VRAM_GB

    def _base_filter(o: dict[str, Any]) -> bool:
        if vram_min is not None and _offer_vram_gb(o) < vram_min:
            return False
        dph = _to_float(o.get("dph_total"))
        if dph is None:
            return False
        if dph_min is not None and dph < dph_min:
            return False
        if dph_max is not None and dph > dph_max:
            return False
        return True

    preferred = [o for o in offers if _base_filter(o)]
    if preferred:
        fastest_perf = max((_offer_perf(o) for o in preferred), default=0.0)
        if fastest_perf > 0:
            speed_floor = max(0.0, min(1.0, settings.VASTAI_FASTEST_SPEED_FRACTION)) * fastest_perf
            near_fast = [o for o in preferred if _offer_perf(o) >= speed_floor]
            if near_fast:
                near_fast.sort(key=lambda o: _offer_profile_rank(o, profile))
                return near_fast
        preferred.sort(key=lambda o: _offer_profile_rank(o, profile))
        return preferred

    # If exact budget not found, keep a best-effort fallback.
    capped = []
    if dph_max is not None:
        capped = [o for o in offers if (_to_float(o.get("dph_total")) or 9999.0) <= dph_max]
    if capped:
        capped = [o for o in capped if (vram_min is None or _offer_vram_gb(o) >= vram_min)]
        capped.sort(key=lambda o: _offer_profile_rank(o, profile))
        return capped

    fallback = [o for o in offers if (vram_min is None or _offer_vram_gb(o) >= vram_min)]
    fallback.sort(key=lambda o: _offer_profile_rank(o, profile))
    return fallback


async def start_instance(selection_profile: str | None = None) -> int | None:
    """
    Start or reuse an existing Vast.ai GPU instance.
    Fallback: search offer and create a new instance.
    Returns instance_id (existing/new) or None on failure.
    """
    if not settings.VASTAI_API_KEY:
        log.warning("Vast.ai API key not configured")
        return None
    resolved_profile = _resolve_selection_profile(selection_profile)

    if settings.VASTAI_REUSE_EXISTING_FIRST or settings.VASTAI_NEVER_CREATE_NEW:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{VASTAI_API_BASE}/instances/",
                headers=_headers(),
            )
            if resp.status_code == 200:
                payload = resp.json()
                instances = payload.get("instances") if isinstance(payload, dict) else None
                instances = instances if isinstance(instances, list) else []

                existing = _pick_existing_instance(instances)
                if settings.VASTAI_PREFERRED_INSTANCE_ID is not None and existing is None:
                    log.warning(
                        "Vast.ai preferred instance %s not found in account instances",
                        settings.VASTAI_PREFERRED_INSTANCE_ID,
                    )
                    if settings.VASTAI_PREFERRED_STRICT:
                        return None
                if existing:
                    instance_id = int(existing["id"])
                    status = _instance_status(existing)
                    if status in {"CONNECT", "OPEN", "RUNNING", "CREATING", "LOADING", "STARTING", "SCHEDULED"}:
                        log.info("Vast.ai reusing existing instance %s (status=%s)", instance_id, status)
                        return instance_id

                    if status in {"INACTIVE", "STOPPED", "EXITED", "OFFLINE"}:
                        start_resp = await client.put(
                            f"{VASTAI_API_BASE}/instances/{instance_id}/",
                            json={"state": "running"},
                            headers=_headers(),
                        )
                        if start_resp.status_code == 200:
                            log.info("Vast.ai started existing instance %s from status=%s", instance_id, status)
                            return instance_id
                        log.warning(
                            "Vast.ai failed to start existing instance %s: %s",
                            instance_id,
                            start_resp.text[:300],
                        )
                        if settings.VASTAI_PREFERRED_INSTANCE_ID is not None and settings.VASTAI_PREFERRED_STRICT:
                            return None
            else:
                log.warning("Vast.ai list instances failed: %s", resp.text[:300])

    if settings.VASTAI_NEVER_CREATE_NEW:
        return None

    # 1) Search offers
    base_search_body: dict[str, Any] = {
        "limit": 20,
        "type": "ondemand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"eq": 1},
    }

    # Try strict filters first, then gracefully relax to avoid false "no offers found".
    search_variants: list[dict[str, Any]] = []
    strict = dict(base_search_body)
    if settings.VASTAI_GPU_NAME:
        strict["gpu_name"] = {"eq": settings.VASTAI_GPU_NAME}
    if settings.VASTAI_RELIABILITY_MIN is not None:
        strict["reliability"] = {"gte": settings.VASTAI_RELIABILITY_MIN}
    dph_total_filter: dict[str, float] = {}
    if settings.VASTAI_DPH_MIN is not None:
        dph_total_filter["gte"] = settings.VASTAI_DPH_MIN
    if settings.VASTAI_DPH_MAX is not None:
        dph_total_filter["lte"] = settings.VASTAI_DPH_MAX
    if dph_total_filter:
        strict["dph_total"] = dph_total_filter
    search_variants.append(strict)

    no_gpu_name = dict(strict)
    no_gpu_name.pop("gpu_name", None)
    search_variants.append(no_gpu_name)

    no_price_limit = dict(no_gpu_name)
    no_price_limit.pop("dph_total", None)
    search_variants.append(no_price_limit)

    relaxed = dict(base_search_body)
    search_variants.append(relaxed)

    offers: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for idx, search_body in enumerate(search_variants, start=1):
            resp = await client.post(
                f"{VASTAI_API_BASE}/bundles/",
                json=search_body,
                headers=_headers(),
            )
            if resp.status_code != 200:
                log.warning("Vast.ai search attempt %d failed: %s", idx, resp.text[:300])
                continue
            data = resp.json()
            offers = data.get("offers") or []
            if offers:
                if idx > 1:
                    log.info("Vast.ai offers found on fallback attempt #%d", idx)
                break

    if not offers:
        log.error("Vast.ai: no offers found for criteria")
        return None

    candidate_offers = _select_offers_for_budget(offers, resolved_profile)
    if not candidate_offers:
        log.error("Vast.ai: no valid offers after budget/power selection")
        return None

    # 2) Create instance from offer
    explicit_cpu_api_base = (settings.VASTAI_CPU_API_BASE_URL or "").strip().rstrip("/")
    webhook_base = (settings.TELEGRAM_WEBHOOK_BASE_URL or "").strip().rstrip("/")
    api_base = explicit_cpu_api_base or (f"{webhook_base}/api/v1" if webhook_base else "")
    if not api_base:
        log.error(
            "Vast.ai start aborted: no public CPU API base URL configured. "
            "Set VASTAI_CPU_API_BASE_URL (preferred) or TELEGRAM_WEBHOOK_BASE_URL."
        )
        return None
    create_body: dict[str, Any] = {
        "image": settings.VASTAI_IMAGE,
        "disk": settings.VASTAI_DISK_GB,
        "runtype": "ssh",
        "target_state": "running",
        "extra_env": {
            "CPU_API_BASE_URL": api_base,
            "GPU_API_KEY": settings.GPU_API_KEY,
            "S3_ENDPOINT_URL": settings.S3_ENDPOINT_URL,
            "S3_ACCESS_KEY": settings.S3_ACCESS_KEY,
            "S3_SECRET_KEY": settings.S3_SECRET_KEY,
            "S3_BUCKET": settings.S3_BUCKET,
        },
    }
    onstart_cmd = _build_onstart_command()
    if onstart_cmd:
        create_body["onstart"] = onstart_cmd

    async with httpx.AsyncClient(timeout=60) as client:
        for idx, offer in enumerate(candidate_offers, start=1):
            offer_id = offer.get("id")
            if offer_id is None:
                continue
            resp = await client.put(
                f"{VASTAI_API_BASE}/asks/{offer_id}/",
                json=create_body,
                headers=_headers(),
            )
            if resp.status_code != 200:
                log.warning(
                    "Vast.ai create attempt %d failed for offer %s (dph=%s, dlperf=%s): %s",
                    idx,
                    offer_id,
                    offer.get("dph_total"),
                    offer.get("dlperf"),
                    resp.text[:200],
                )
                continue

            result = resp.json()
            instance_id = result.get("new_contract")
            if instance_id is None:
                log.warning(
                    "Vast.ai create attempt %d got no new_contract for offer %s: %s",
                    idx,
                    offer_id,
                    str(result)[:200],
                )
                continue

            perf = _offer_perf(offer)
            est_cost = (_offer_dph(offer) / perf) if perf > 0 else None
            log.info(
                "Vast.ai instance created: %s from offer %s (profile=%s, dph=%s, perf=%s, est_cost_per_work=%s)",
                instance_id,
                offer_id,
                resolved_profile,
                offer.get("dph_total"),
                perf,
                f"{est_cost:.6f}" if est_cost is not None else "n/a",
            )
            return int(instance_id)

    log.error("Vast.ai create instance failed for all candidate offers")
    return None


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


async def start_existing_instance(instance_id: int) -> bool:
    """Start an already existing Vast.ai instance (state=running)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{VASTAI_API_BASE}/instances/{instance_id}/",
            json={"state": "running"},
            headers=_headers(),
        )
    ok = resp.status_code == 200
    log.info("Vast.ai start existing instance %s: %s", instance_id, "OK" if ok else resp.text[:200])
    return ok


async def stop_instance(instance_id: int) -> bool:
    """Stop (do not destroy) a Vast.ai instance to preserve disk/cache."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{VASTAI_API_BASE}/instances/{instance_id}/",
            json={"state": "stopped"},
            headers=_headers(),
        )
    ok = resp.status_code == 200
    log.info("Vast.ai stop instance %s: %s", instance_id, "OK" if ok else resp.text[:200])
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
