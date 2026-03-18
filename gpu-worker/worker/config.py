from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    CPU_API_BASE_URL: str
    GPU_API_KEY: str

    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str

    WHISPER_MODEL_NAME: str = "openai/whisper-large-v3"
    WHISPER_DEVICE: str = "cuda"
    WHISPER_BATCH_SIZE: int = 24
    WHISPER_USE_FLASH_ATTN: bool = True
    WHISPER_MODEL_DIR: str = "/root/.cache/whisperx"

    WORKER_ID: str = "gpu-worker-1"
    POLL_INTERVAL_SEC: int = 10
    IDLE_SHUTDOWN_SEC: int = 60   # shut down 60 s after last job finishes
    JOB_MAX_DURATION_SEC: int = 7200  # 2-hour hard limit per job
    WORK_DIR: str = "/tmp/clips_worker"
    LOG_LEVEL: str = "INFO"


settings = WorkerSettings()
