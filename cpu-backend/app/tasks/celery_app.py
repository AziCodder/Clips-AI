from __future__ import annotations

from celery import Celery

from app.core.config import settings

app = Celery(
    "clips",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.pipeline_tasks",
        "app.tasks.schedule",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.SCHEDULER_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.pipeline_tasks.task_search_candidates": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_download_approved": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_start_gpu_pod": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_run_llm_analysis": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_render_clips_batch": {"queue": "clips"},
        "app.tasks.pipeline_tasks.task_send_daily_notification": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_reaper": {"queue": "default"},
        "app.tasks.pipeline_tasks.task_ensure_gpu_running": {"queue": "pipeline"},
        "app.tasks.pipeline_tasks.task_destroy_idle_gpu": {"queue": "default"},
    },
)
