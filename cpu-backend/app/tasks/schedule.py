from __future__ import annotations

from celery.schedules import crontab

from app.tasks.celery_app import app

# All times are in Europe/Moscow (set by app.conf.timezone)
app.conf.beat_schedule = {
    # 08:00 MSK — search video candidates for all enabled topics
    "search-candidates": {
        "task": "app.tasks.pipeline_tasks.task_search_candidates",
        "schedule": crontab(hour=8, minute=0),
    },
    # 11:00 MSK — download approved videos + extract audio + upload to S3
    # (queues transcription jobs and starts GPU automatically on completion)
    "download-approved": {
        "task": "app.tasks.pipeline_tasks.task_download_approved",
        "schedule": crontab(hour=11, minute=0),
    },
    # 01:00 MSK — LLM analysis of transcribed videos
    "llm-analysis": {
        "task": "app.tasks.pipeline_tasks.task_run_llm_analysis",
        "schedule": crontab(hour=1, minute=0),
    },
    # 04:00 MSK — render clips via ffmpeg
    "render-clips": {
        "task": "app.tasks.pipeline_tasks.task_render_clips_batch",
        "schedule": crontab(hour=4, minute=0),
    },
    # 06:00 MSK — send daily "clips ready" notification
    "daily-notification": {
        "task": "app.tasks.pipeline_tasks.task_send_daily_notification",
        "schedule": crontab(hour=6, minute=0),
    },
    # Every 15 min — reaper for stale/hung jobs
    "reaper": {
        "task": "app.tasks.pipeline_tasks.task_reaper",
        "schedule": crontab(minute="*/15"),
    },
    # Every 2 min — destroy idle GPU instance when no jobs left (stops billing)
    "destroy-idle-gpu": {
        "task": "app.tasks.pipeline_tasks.task_destroy_idle_gpu",
        "schedule": crontab(minute="*/2"),
    },
}
