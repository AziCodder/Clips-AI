# Deployment Guide — Clips MVP

## CPU Server (always on)

### 1. Clone and configure
```bash
git clone <repo> clips
cd clips
cp infra/env/cpu-backend.env.example infra/env/cpu-backend.env
# Edit infra/env/cpu-backend.env with real credentials
```

### 2. Start all CPU services
```bash
docker compose -f infra/docker-compose.cpu.yml up -d
```

### 3. Run DB migrations
```bash
docker compose -f infra/docker-compose.cpu.yml exec api \
  alembic -c alembic.ini upgrade head
```

### 4. Build and deploy frontend
```bash
cd frontend
cp ../infra/env/frontend.env.example .env.local
# Edit VITE_API_BASE_URL
npm install
npm run build
# dist/ folder is served by nginx container automatically
```

### 5. Set Telegram webhook
The webhook is set automatically on API startup.
To verify: `GET /api/v1/telegram/health`

---

## GPU Server (Vast.ai On-Demand)

The GPU server is started **automatically** by the CPU server at **14:00 Moscow time** via Vast.ai API.

### Manual setup (one-time on Vast.ai instance / template)
On the rented Vast.ai machine (or your own image):
```bash
cd /root
git clone <repo> clips
cd clips/gpu-worker
cp ../infra/env/gpu-worker.env.example .env
# Edit .env: CPU_API_BASE_URL, GPU_API_KEY, S3 credentials
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Pre-download WhisperX model:
python -c "import whisperx; whisperx.load_model('large-v3', 'cuda', compute_type='float16')"
```

The worker starts automatically via `systemd` (see `infra/systemd/gpu-worker.service.example`).

The worker shuts itself down after 15 minutes of idle (no jobs).

---

## Pipeline Schedule (Europe/Moscow)

| Time | Stage |
|------|-------|
| 08:00–11:00 | Search video candidates + TG approval |
| 11:00–13:00 | Download approved videos + extract audio |
| 14:00 | CPU starts Vast.ai GPU instance |
| 15:00–01:00 | GPU transcribes audio (1 job at a time) |
| 01:00–04:00 | LLM highlights analysis |
| 04:00–06:00 | Clip rendering (ffmpeg on CPU) |
| 06:00 | TG notification "clips ready" |
| Every 15 min | Reaper: check stale jobs |

---

## Key Environment Variables

### CPU Backend
- `DATABASE_URL` — async PostgreSQL URL
- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `TELEGRAM_WEBHOOK_BASE_URL` — your HTTPS domain
- `GPU_API_KEY` — shared secret for GPU↔CPU auth
- `S3_*` — HostKey S3 credentials
- `VASTAI_API_KEY` — Vast.ai API key (from cloud.vast.ai); optional `VASTAI_GPU_NAME`, `VASTAI_IMAGE`, `VASTAI_DISK_GB`
- `OPENAI_API_KEY` — for LLM highlights (or set `LLM_USE_MOCK=true`)
- `YOUTUBE_DATA_API_KEY` — for YouTube search

### GPU Worker
- `CPU_API_BASE_URL` — e.g. `https://your-domain.com/api/v1`
- `GPU_API_KEY` — must match CPU setting
- `S3_*` — same bucket, separate credentials recommended
