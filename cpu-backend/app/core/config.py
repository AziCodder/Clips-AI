from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # ── Redis / Celery ────────────────────────────────────────────────────
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # ── S3 ────────────────────────────────────────────────────────────────
    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str
    S3_PRESIGNED_TTL: int = 3600

    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str
    TELEGRAM_WEBHOOK_BASE_URL: str

    # ── GPU API auth ──────────────────────────────────────────────────────
    GPU_API_KEY: str
    GPU_IP_ALLOWLIST: str = ""  # comma-separated IPs; empty = disabled

    # ── Vast.ai (GPU cloud) ───────────────────────────────────────────────
    VASTAI_API_KEY: str = ""
    # Publicly reachable CPU API base for GPU workers, e.g. https://api.example.com/api/v1
    VASTAI_CPU_API_BASE_URL: str = ""
    VASTAI_IMAGE: str = "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime"
    VASTAI_DISK_GB: int = 30
    VASTAI_GPU_NAME: str = ""  # e.g. "RTX_4090" or "RTX_3090"; empty = any
    VASTAI_DPH_MIN: float | None = 0.2  # min $/hour for fallback offer selection
    VASTAI_RELIABILITY_MIN: float | None = 0.9
    VASTAI_DPH_MAX: float | None = 0.5  # max $/hour; None = no limit
    VASTAI_ONSTART: str = ""
    VASTAI_INSTANCE_START_TIMEOUT_SEC: int = 600
    VASTAI_POLL_INTERVAL_SEC: int = 60
    VASTAI_MIN_VRAM_GB: float | None = 24.0  # skip weak cards for Whisper workloads
    VASTAI_FASTEST_SPEED_FRACTION: float = 0.8  # keep offers at least X% of fastest
    VASTAI_SELECTION_PROFILE: str = "auto"  # auto|speed|balanced|economy
    VASTAI_PROFILE_SPEED_QUEUE_MIN: int = 4
    VASTAI_PROFILE_SPEED_TOTAL_MINUTES_MIN: int = 180
    VASTAI_PROFILE_ECONOMY_QUEUE_MAX: int = 1
    VASTAI_PROFILE_ECONOMY_TOTAL_MINUTES_MAX: int = 40
    VASTAI_PREFERRED_INSTANCE_ID: int | None = None  # explicit existing instance to reuse/start
    VASTAI_REUSE_EXISTING_FIRST: bool = True
    VASTAI_PREFERRED_STRICT: bool = False  # True => fail if preferred instance not usable

    @field_validator(
        "VASTAI_DPH_MIN",
        "VASTAI_RELIABILITY_MIN",
        "VASTAI_DPH_MAX",
        "VASTAI_MIN_VRAM_GB",
        "VASTAI_PREFERRED_INSTANCE_ID",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v

    @field_validator("VASTAI_SELECTION_PROFILE", mode="before")
    @classmethod
    def normalize_selection_profile(cls, v):
        val = str(v or "auto").strip().lower()
        allowed = {"auto", "speed", "balanced", "economy"}
        if val not in allowed:
            return "auto"
        return val

    # ── YouTube / Search ──────────────────────────────────────────────────
    YOUTUBE_DATA_API_KEY: str = ""
    SEARCH_MAX_VIDEOS_PER_TOPIC: int = 3
    SEARCH_MAX_TOTAL_DURATION_MIN: int = 360
    # Путь к файлу cookies (Netscape/JSON) для yt-dlp. Задаётся через env (docker-compose).
    # Значение по умолчанию — пустая строка; путь обязательно в кавычках, если задаёте здесь.
    # См. docs/YOUTUBE_COOKIES.md
    YTDLP_COOKIES_FILE: str = ""

    # ── LLM ───────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_USE_MOCK: bool = False

    # ── Scheduler ─────────────────────────────────────────────────────────
    SCHEDULER_TIMEZONE: str = "Europe/Moscow"

    # ── ffmpeg ────────────────────────────────────────────────────────────
    FFMPEG_MAX_CONCURRENT: int = 2
    FFMPEG_THREADS: int = 2

    # ── Reaper ────────────────────────────────────────────────────────────
    REAPER_INTERVAL_SEC: int = 900
    JOB_LEASE_TTL_HOURS: int = 4
    JOB_MAX_ATTEMPTS: int = 3

    # ── Frontend ───────────────────────────────────────────────────────────
    # Full origin of the frontend, e.g. https://your-domain.com (used for CORS in production)
    FRONTEND_ORIGIN: str = ""

    # ── Environment ───────────────────────────────────────────────────────
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    @property
    def gpu_ip_allowlist_set(self) -> set[str]:
        if not self.GPU_IP_ALLOWLIST:
            return set()
        return {ip.strip() for ip in self.GPU_IP_ALLOWLIST.split(",") if ip.strip()}


settings = Settings()
