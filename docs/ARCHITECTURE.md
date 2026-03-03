# Architecture — Clips MVP

## Services Overview

```
┌─────────────────────────────────────────────────────────────┐
│ CPU Server (always on)                                      │
│                                                             │
│  ┌─────────────┐  ┌────────────────┐  ┌─────────────────┐  │
│  │ FastAPI API │  │ Celery Worker  │  │  Celery Beat    │  │
│  │  :8000      │  │  (pipeline)    │  │  (scheduler)    │  │
│  └──────┬──────┘  └───────┬────────┘  └────────┬────────┘  │
│         │                 │                     │           │
│  ┌──────▼─────────────────▼─────────────────────▼────────┐  │
│  │              Postgres + Redis                         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────┐   ┌─────────────────┐                 │
│  │  aiogram Bot    │   │  Nginx + React  │                 │
│  │  (webhook)      │   │  frontend       │                 │
│  └─────────────────┘   └─────────────────┘                 │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS + S3
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ GPU Server (Vast.ai On-Demand — CPU запускает при задачах)   │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  GPU Worker (WhisperX large-v3)                       │  │
│  │  - Polls CPU /api/v1/gpu/jobs/next                    │  │
│  │  - Downloads audio from S3                            │  │
│  │  - Transcribes + aligns (1 job at a time)             │  │
│  │  - Uploads results to S3                              │  │
│  │  - Reports completed/failed to CPU                    │  │
│  │  - Exits after 60s idle → CPU destroys instance       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ S3 (HostKey) — Private bucket                               │
│  videos/{video_id}/master.mp4                               │
│  videos/{video_id}/audio/audio.flac                         │
│  videos/{video_id}/transcripts/{job_id}/...                 │
│  videos/{video_id}/clips/{clip_id}/clip.mp4                 │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Search** (08:00 MSK): CPU searches YouTube → dry-run check → creates `pending_approval` + sends TG
2. **Approval** (async): User presses Approve/Reject in Telegram → status updated in DB
3. **Ingest** (11:00 MSK или сразу при одобрении): CPU downloads `approved` videos → extracts audio → uploads to S3
4. **GPU start** (сразу после завершения скачивания): CPU вызывает Vast.ai API → instance starts → worker polls for jobs
5. **Transcription**: GPU polls `/gpu/jobs/next` → processes 1 job → uploads to S3 → CPU ACKs
6. **LLM analysis** (01:00–04:00): CPU reads transcript from S3 → LLM extracts highlights → saves to DB
7. **Clip rendering** (04:00–06:00): CPU downloads master video → cuts clips → uploads to S3
8. **Notification** (06:00): CPU sends TG message "clips ready"

## Security

- GPU API: Bearer token + IP allowlist — no public access
- S3: Private bucket, frontend only gets presigned URLs
- Frontend never receives `s3_key`, only presigned URLs
- Telegram webhook: secret token validation
