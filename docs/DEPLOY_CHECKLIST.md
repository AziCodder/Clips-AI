# Чеклист перед деплоем

## Автоматика CPU ↔ GPU

- **CPU запускает GPU** когда есть задачи (после скачивания или утреннего поиска)
- **GPU выключается** через 60 сек после последней задачи; CPU каждые 2 мин уничтожает инстанс Vast.ai
- **Ручная ссылка**: добавь видео с `auto_approve: true` — сразу скачивание → GPU → транскрипция

## 1. CPU-сервер (`infra/env/cpu-backend.env`)

| Переменная | Действие |
|------------|----------|
| `SECRET_KEY` | Сгенерировать: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GPU_API_KEY` | Сгенерировать (тот же ключ — в gpu-worker) |
| `TELEGRAM_WEBHOOK_BASE_URL` | Ваш домен, напр. `https://clips.yourdomain.com` |
| `TELEGRAM_WEBHOOK_SECRET` | Сгенерировать для вебхука |
| `VASTAI_API_KEY` | Ключ из cloud.vast.ai → Account → API Keys |
| `YOUTUBE_DATA_API_KEY` | Ключ из Google Cloud Console |
| `OPENAI_API_KEY` | Ключ OpenAI |
| `ENV` | Поставить `production` для продакшена |

## 2. GPU-сервер (Vast.ai 217.171.200.22)

**Если инстанс уже арендован вручную** — запуск воркера вручную:

```bash
ssh root@217.171.200.22
cd /root
git clone https://github.com/AziCodder/Clips-AI.git clips
cd clips/gpu-worker
cp .env.example .env
# Отредактировать .env: CPU_API_BASE_URL, GPU_API_KEY, S3_*
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -c "import whisperx; whisperx.load_model('large-v3', 'cuda', compute_type='float16'); print('OK')"
nohup python3 -m worker.main >> /var/log/gpu-worker.log 2>&1 &
```

**Если CPU запускает инстанс через API** — env передаётся автоматически. Убедись, что `TELEGRAM_WEBHOOK_BASE_URL` задан (от него строится `CPU_API_BASE_URL`).

## 3. Проверки

- [ ] `GPU_IP_ALLOWLIST` содержит IP GPU-сервера (217.171.200.22)
- [ ] `GPU_API_KEY` одинаковый на CPU и GPU
- [ ] `TELEGRAM_WEBHOOK_BASE_URL` — без слэша в конце
- [ ] S3 credentials совпадают на CPU и GPU
