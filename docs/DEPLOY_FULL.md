# DEPLOY_FULL.md — Полный гайд деплоя CLIP AI

> Документ охватывает всё: от аренды сервера до работающего pipeline в продакшене.
> Читай сверху вниз, не пропускай шаги.

---

## Оглавление

1. [Архитектура системы](#1-архитектура-системы)
2. [Требования к серверам](#2-требования-к-серверам)
3. [Подготовка CPU-сервера](#3-подготовка-cpu-сервера)
4. [Установка Docker](#4-установка-docker)
5. [Настройка домена и SSL](#5-настройка-домена-и-ssl)
6. [Клонирование кода и настройка .env](#6-клонирование-кода-и-настройка-env)
7. [Запуск всех сервисов](#7-запуск-всех-сервисов)
8. [Миграции базы данных](#8-миграции-базы-данных)
9. [Настройка S3 (HostKey)](#9-настройка-s3-hostkey)
10. [Настройка Telegram-бота](#10-настройка-telegram-бота)
11. [GPU-воркер на Vast.ai](#11-gpu-воркер-на-vastai)
12. [Первый запуск и проверка pipeline](#12-первый-запуск-и-проверка-pipeline)
13. [Обновление кода в продакшене](#13-обновление-кода-в-продакшене)
14. [Мониторинг и обслуживание](#14-мониторинг-и-обслуживание)
15. [Резервное копирование](#15-резервное-копирование)
16. [Расписание pipeline](#16-расписание-pipeline)

---

## 1. Архитектура системы

```
Internet
   │
   ▼
[Nginx + SSL]  ←── Let's Encrypt (порт 443)
   │
   ├──/api/v1/*──► [FastAPI API]  ──► [PostgreSQL]
   │                    │         ──► [Redis]
   │              [Celery Beat]   ──► [Celery Worker]
   │              [Telegram Bot]
   │
   └──/*──────────► [Frontend React SPA]

                   [S3 HostKey]  ◄──► API + GPU Worker

                   [Vast.ai GPU] ◄──► CPU API (polling)
                                       WhisperX transcription
```

**Сервисы в docker-compose:**
| Сервис | Назначение |
|---|---|
| `postgres` | База данных |
| `redis` | Брокер Celery + кэш |
| `api` | FastAPI, uvicorn 2 workers |
| `celery_worker` | Фоновые задачи pipeline |
| `celery_beat` | Планировщик (crontab) |
| `bot` | Telegram бот (polling) |
| `frontend` | React SPA (nginx) |

GPU-воркер запускается **отдельно на Vast.ai** — CPU-сервер запускает его автоматически через API Vast.ai.

---

## 2. Требования к серверам

### CPU-сервер (всегда включён)

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| SSD | 40 GB | 80 GB |
| ОС | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Порты | 22, 80, 443 | 22, 80, 443 |

Подходящие провайдеры: **Hetzner** (CX21/CX31), **DigitalOcean** (2-4 GB Droplet), **Contabo**, **Selectel**.

### GPU-воркер (по требованию, Vast.ai)

- GPU: RTX 4090 / RTX 3090 / A100 (настраивается в `VASTAI_GPU_NAME`)
- RAM: 16+ GB
- VRAM: 16+ GB (WhisperX large-v3)
- Диск: 32 GB (настраивается в `VASTAI_DISK_GB`)

---

## 3. Подготовка CPU-сервера

Подключись по SSH от root:

```bash
ssh root@YOUR_SERVER_IP
```

### Создание не-root пользователя

```bash
adduser deploy
usermod -aG sudo deploy
# Скопировать SSH-ключи для нового пользователя
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

### Обновление системы

```bash
apt update && apt upgrade -y
apt install -y curl wget git unzip htop
```

### Настройка файрвола

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

---

## 4. Установка Docker

```bash
# Установить Docker CE
curl -fsSL https://get.docker.com | sh

# Добавить пользователя deploy в группу docker
usermod -aG docker deploy

# Проверить установку
docker --version
docker compose version
```

> Перелогинься под `deploy` чтобы группа docker применилась:
> `su - deploy`

---

## 5. Настройка домена и SSL

### Шаг 1. Направить домен на сервер

В DNS-панели (где куплен домен) создай A-запись:
```
your-domain.com  →  YOUR_SERVER_IP
```
Изменения DNS распространяются до 24 часов (обычно 5–15 минут).

### Шаг 2. Установить Nginx + Certbot

```bash
apt install -y nginx certbot python3-certbot-nginx
```

### Шаг 3. Создать конфиг Nginx для домена

```bash
cat > /etc/nginx/sites-available/clips << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # SPA и статика фронтенда
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 120s;
    }

    # Telegram webhook
    location /telegram/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/clips /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

> Замени `your-domain.com` на свой реальный домен.

### Шаг 4. Получить SSL-сертификат

```bash
certbot --nginx -d your-domain.com
# Следуй инструкциям:
# - введи email
# - согласись с условиями (A)
# - выбери redirect HTTP→HTTPS (2)
```

Проверь автообновление:
```bash
certbot renew --dry-run
```

Certbot автоматически добавит таймер `systemd` для обновления сертификата каждые 60 дней.

---

## 6. Клонирование кода и настройка .env

### Клонировать репозиторий

```bash
su - deploy
cd /home/deploy
git clone https://github.com/YOUR_ORG/YOUR_REPO.git clips
cd clips
```

### Создать .env файл

```bash
cp infra/env/cpu-backend.env.example infra/env/cpu-backend.env
nano infra/env/cpu-backend.env
```

**Заполни все переменные:**

```bash
# ── Database ──────────────────────────────────────────────────────────────────
# Пароль БД — придумай сложный, только латиница и цифры
DATABASE_URL=postgresql+asyncpg://clips:СЮДА_ПАРОЛЬ_БД@postgres:5432/clips
SYNC_DATABASE_URL=postgresql://clips:СЮДА_ПАРОЛЬ_БД@postgres:5432/clips

# ── Security ──────────────────────────────────────────────────────────────────
# Сгенерировать: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=СГЕНЕРИРОВАННЫЙ_КЛЮЧ_64_СИМВОЛА

# ── S3 ────────────────────────────────────────────────────────────────────────
S3_ENDPOINT_URL=https://s3-nl.hostkey.com
S3_ACCESS_KEY=ТВОЙ_КЛЮЧ_ДОСТУПА_S3
S3_SECRET_KEY=ТВОЙ_СЕКРЕТНЫЙ_КЛЮЧ_S3
S3_BUCKET=bc4d77ea-clips-ai-s3-storage190904

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=ТОКЕН_ОТ_BOTFATHER
# Сгенерировать: python3 -c "import secrets; print(secrets.token_hex(16))"
TELEGRAM_WEBHOOK_SECRET=СЛУЧАЙНАЯ_СТРОКА
TELEGRAM_WEBHOOK_BASE_URL=https://your-domain.com

# ── CORS (фронтенд) ───────────────────────────────────────────────────────────
FRONTEND_ORIGIN=https://your-domain.com

# ── GPU API auth ──────────────────────────────────────────────────────────────
# Сгенерировать: python3 -c "import secrets; print(secrets.token_hex(32))"
GPU_API_KEY=СГЕНЕРИРОВАННЫЙ_КЛЮЧ
# IP адреса Vast.ai инстансов (можно оставить пустым если не нужно ограничение)
GPU_IP_ALLOWLIST=

# ── Vast.ai ───────────────────────────────────────────────────────────────────
# API ключ с cloud.vast.ai → Account → API Keys
VASTAI_API_KEY=ТВОЙ_VASTAI_API_KEY
VASTAI_GPU_NAME=RTX_4090
VASTAI_DISK_GB=32
VASTAI_DPH_MAX=1.5

# ── YouTube ───────────────────────────────────────────────────────────────────
# console.cloud.google.com → APIs → YouTube Data API v3 → Credentials
YOUTUBE_DATA_API_KEY=ТВОЙ_YT_API_KEY

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-...ТВОЙ_КЛЮЧ

# ── Окружение ─────────────────────────────────────────────────────────────────
ENV=production
LOG_LEVEL=INFO
```

### Настроить пароль PostgreSQL в docker-compose

Открой `infra/docker-compose.cpu.yml` и замени пароль PostgreSQL на тот же что в `.env`:

```bash
nano infra/docker-compose.cpu.yml
```

Найди секцию `postgres` и измени:
```yaml
environment:
  POSTGRES_USER: clips
  POSTGRES_PASSWORD: СЮДА_ТОТ_ЖЕ_ПАРОЛЬ_БД   # ← заменить
  POSTGRES_DB: clips
```

---

## 7. Запуск всех сервисов

```bash
cd /home/deploy/clips

# Сборка образов и запуск в фоне
docker compose -f infra/docker-compose.cpu.yml up -d --build

# Проверить что все контейнеры запустились
docker compose -f infra/docker-compose.cpu.yml ps
```

Ожидаемый вывод — все сервисы в статусе `Up` или `running`:
```
NAME              STATUS
clips-postgres    Up (healthy)
clips-redis       Up (healthy)
clips-api         Up
clips-celery_worker  Up
clips-celery_beat    Up
clips-bot            Up
clips-frontend       Up
```

Если какой-то контейнер не запускается:
```bash
docker compose -f infra/docker-compose.cpu.yml logs api
docker compose -f infra/docker-compose.cpu.yml logs celery_worker
```

---

## 8. Миграции базы данных

```bash
docker compose -f infra/docker-compose.cpu.yml exec api \
  alembic -c alembic.ini upgrade head
```

Ожидаемый вывод:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial
```

### Создать первого пользователя

```bash
docker compose -f infra/docker-compose.cpu.yml exec api python3 -c "
import asyncio
from app.db.session import get_async_session
from app.core.security import get_password_hash
from app.db.models import User
import uuid
from datetime import datetime, timezone

async def create_user():
    async for db in get_async_session():
        user = User(
            id=uuid.uuid4(),
            email='admin@example.com',
            password_hash=get_password_hash('ВАШ_ПАРОЛЬ'),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        print('User created:', user.email)

asyncio.run(create_user())
"
```

Или через API после запуска:
```bash
curl -X POST https://your-domain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ВАШ_ПАРОЛЬ"}'
```

### Проверить работу API

```bash
curl https://your-domain.com/api/v1/health
# Ожидаемый ответ: {"status":"ok"}
```

---

## 9. Настройка S3 (HostKey)

### Создание бакета в панели HostKey

1. Зайди в панель: [https://panel.hostkey.com](https://panel.hostkey.com)
2. Перейди в раздел **Object Storage**
3. Нажми **Create Bucket**
4. Имя бакета: например `clips-production`
5. Регион: Netherlands (или ближайший)
6. Создай **Access Key** и **Secret Key** — скопируй в `.env`

### Настройка CORS-политики бакета

В настройках бакета → CORS Policy добавь:

```json
[
  {
    "AllowedOrigins": ["https://your-domain.com"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

### Проверка доступа к S3

```bash
docker compose -f infra/docker-compose.cpu.yml exec api python3 -c "
from app.services import s3_service
keys = s3_service.list_keys('test/')
print('S3 OK, keys:', keys[:3])
"
```

---

## 10. Настройка Telegram-бота

### Создать бота (если ещё нет)

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → введи имя → получи токен
3. Скопируй токен в `TELEGRAM_BOT_TOKEN` в `.env`

### Узнать свой Telegram ID

Напиши боту [@userinfobot](https://t.me/userinfobot) — он пришлёт твой числовой ID.

### Обновить пользователя с telegram_id

```bash
curl -X POST https://your-domain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ВАШ_ПАРОЛЬ"}'
# Скопируй access_token из ответа

curl -X PATCH https://your-domain.com/api/v1/auth/me \
  -H "Authorization: Bearer ВАШ_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": ТВОЙ_TELEGRAM_ID}'
```

### Установить webhook

Бот работает в режиме **polling** (отдельный контейнер `bot`), webhook не нужен.
Для проверки статуса бота:

```bash
docker compose -f infra/docker-compose.cpu.yml logs bot --tail=20
```

Если хочешь webhook (например через Nginx), добавь в `cpu-backend.env`:
```bash
TELEGRAM_WEBHOOK_BASE_URL=https://your-domain.com
```

И вызови endpoint вручную:
```bash
curl -X POST https://your-domain.com/api/v1/telegram/set-webhook \
  -H "Authorization: Bearer ВАШ_ACCESS_TOKEN"
```

---

## 11. GPU-воркер на Vast.ai

### Шаг 1. Создать аккаунт и получить API-ключ

1. Зайди на [https://cloud.vast.ai](https://cloud.vast.ai)
2. Account → API Keys → Create
3. Скопируй ключ в `VASTAI_API_KEY` в `.env`

### Шаг 2. Подготовить образ воркера (один раз)

GPU-воркер запускается CPU-сервером автоматически через Vast.ai API.
Но нужно подготовить скрипт автозапуска.

Создай файл `infra/vastai-onstart.sh`:

```bash
cat > /home/deploy/clips/infra/vastai-onstart.sh << 'SCRIPT'
#!/bin/bash
set -e

# Установка зависимостей
apt-get update -qq
apt-get install -y -qq git python3-pip python3-venv ffmpeg

# Клонирование репо
cd /root
if [ ! -d "clips" ]; then
  git clone https://YOUR_REPO_URL.git clips
fi
cd clips
git pull

# Настройка virtualenv
cd gpu-worker
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet -r requirements.txt

# Написать .env
cat > .env << 'ENV'
CPU_API_BASE_URL=https://your-domain.com/api/v1
GPU_API_KEY=ВАШ_GPU_API_KEY
S3_ENDPOINT_URL=https://s3-nl.hostkey.com
S3_ACCESS_KEY=ВАШ_S3_ACCESS_KEY
S3_SECRET_KEY=ВАШ_S3_SECRET_KEY
S3_BUCKET=bc4d77ea-clips-ai-s3-storage190904
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WORKER_ID=vastai-worker-1
ENV

# Предзагрузка модели WhisperX (один раз — кэшируется)
python3 -c "
import whisperx
model = whisperx.load_model('large-v3', 'cuda', compute_type='float16')
print('Model loaded OK')
"

# Запуск воркера
nohup python3 -m worker.main >> /var/log/gpu-worker.log 2>&1 &
echo "GPU worker started, PID=$!"
SCRIPT

chmod +x /home/deploy/clips/infra/vastai-onstart.sh
```

### Шаг 3. Настроить VASTAI_ONSTART в .env

В `cpu-backend.env` заполни `VASTAI_ONSTART` командой запуска:

```bash
VASTAI_ONSTART=bash /root/clips/infra/vastai-onstart.sh
```

Или можно поместить весь скрипт как одну строку (экранировав переносы строк).
Рекомендуется хранить скрипт в репо и запускать через `curl`.

### Шаг 4. Настроить GPU-сервер вручную (первый раз)

Для первого запуска и предзагрузки модели:

1. В консоли Vast.ai выбери машину с RTX 4090
2. Образ: `pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime`
3. Диск: 32 GB
4. Подключись по SSH и выполни:

```bash
# На GPU-сервере Vast.ai
apt-get update && apt-get install -y git python3-pip python3-venv
cd /root
git clone https://YOUR_REPO_URL.git clips
cd clips/gpu-worker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Предзагрузить модель (займёт 5–10 минут, ~3 GB)
python3 -c "
import whisperx
model = whisperx.load_model('large-v3', 'cuda', compute_type='float16')
print('WhisperX large-v3 loaded OK')
"
```

После предзагрузки модель будет в `/root/.cache/whisperx` — при последующих запусках загрузится быстро.

### Шаг 5. Проверить автозапуск

CPU-сервер запускает GPU-воркер автоматически в 14:00 МСК через задачу `task_start_gpu_pod`.

Запустить вручную для теста:
```bash
docker compose -f infra/docker-compose.cpu.yml exec celery_worker \
  python3 -m celery -A app.tasks.celery_app call app.tasks.pipeline_tasks.task_start_gpu_pod
```

Проверить логи:
```bash
docker compose -f infra/docker-compose.cpu.yml logs celery_worker --tail=50
```

---

## 12. Первый запуск и проверка pipeline

### Открыть фронтенд

Перейди на `https://your-domain.com` — должна открыться страница входа.

Войди с email/паролем, созданным на шаге 8.

### Создать тематику

В разделе **Тематики** (Topics):
- Нажми «Добавить»
- Название: например `Технологии`
- Keywords: `AI, ChatGPT, нейросети`
- Клипов с видео: `3`
- Промпт: `Выбери самые интересные и информативные моменты`

### Добавить тестовое видео вручную

В разделе **Видео** → поле URL:
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Нажми **Добавить** → видео появится со статусом `PENDING_APPROVAL`.

### Одобрить видео через Telegram

Запустить поиск видео и отправку в Telegram вручную:
```bash
docker compose -f infra/docker-compose.cpu.yml exec celery_worker \
  python3 -m celery -A app.tasks.celery_app call \
  app.tasks.pipeline_tasks.task_search_candidates
```

В Telegram-боте придёт сообщение с кнопками одобрить/отклонить.

### Запустить скачивание вручную

```bash
docker compose -f infra/docker-compose.cpu.yml exec celery_worker \
  python3 -m celery -A app.tasks.celery_app call \
  app.tasks.pipeline_tasks.task_download_approved
```

### Мониторинг задач Celery

```bash
# Список активных задач
docker compose -f infra/docker-compose.cpu.yml exec celery_worker \
  celery -A app.tasks.celery_app inspect active

# Список запланированных задач
docker compose -f infra/docker-compose.cpu.yml exec celery_beat \
  celery -A app.tasks.celery_app inspect scheduled

# Логи воркера в реальном времени
docker compose -f infra/docker-compose.cpu.yml logs -f celery_worker
```

---

## 13. Обновление кода в продакшене

```bash
cd /home/deploy/clips

# Получить последние изменения
git pull origin master

# Пересобрать и перезапустить только изменённые сервисы
docker compose -f infra/docker-compose.cpu.yml up -d --build

# Если были изменения в БД — выполнить миграции
docker compose -f infra/docker-compose.cpu.yml exec api \
  alembic -c alembic.ini upgrade head

# Проверить что всё запустилось
docker compose -f infra/docker-compose.cpu.yml ps
```

> При обновлении пересборка занимает 1–3 минуты. API недоступен в это время.
> Для zero-downtime нужен blue-green деплой — для MVP достаточно стандартного.

---

## 14. Мониторинг и обслуживание

### Просмотр логов

```bash
# Все сервисы (последние 100 строк)
docker compose -f infra/docker-compose.cpu.yml logs --tail=100

# Конкретный сервис в реальном времени
docker compose -f infra/docker-compose.cpu.yml logs -f api
docker compose -f infra/docker-compose.cpu.yml logs -f celery_worker
docker compose -f infra/docker-compose.cpu.yml logs -f bot

# Логи за последний час
docker compose -f infra/docker-compose.cpu.yml logs --since=1h api
```

### Проверка здоровья

```bash
# API health
curl https://your-domain.com/api/v1/health

# PostgreSQL
docker compose -f infra/docker-compose.cpu.yml exec postgres \
  pg_isready -U clips

# Redis
docker compose -f infra/docker-compose.cpu.yml exec redis \
  redis-cli ping

# Размер диска
df -h
du -sh /var/lib/docker/volumes/*
```

### Перезапуск сервисов

```bash
# Перезапустить конкретный сервис
docker compose -f infra/docker-compose.cpu.yml restart api

# Перезапустить всё
docker compose -f infra/docker-compose.cpu.yml restart
```

### Очистка диска (при необходимости)

```bash
# Удалить неиспользуемые образы и кэш сборки
docker system prune -f

# Удалить старые логи Docker
truncate -s 0 /var/lib/docker/containers/*/*-json.log
```

---

## 15. Резервное копирование

### PostgreSQL — ежедневный дамп

Создай скрипт `/home/deploy/backup-db.sh`:

```bash
cat > /home/deploy/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/deploy/backups/postgres"
DATE=$(date +%Y-%m-%d_%H-%M)
mkdir -p "$BACKUP_DIR"

docker compose -f /home/deploy/clips/infra/docker-compose.cpu.yml exec -T postgres \
  pg_dump -U clips clips | gzip > "$BACKUP_DIR/clips_$DATE.sql.gz"

# Оставить только последние 7 дней
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "Backup done: clips_$DATE.sql.gz"
EOF

chmod +x /home/deploy/backup-db.sh
```

Добавить в crontab (запускать каждый день в 03:00):
```bash
crontab -e
# Добавить строку:
0 3 * * * /home/deploy/backup-db.sh >> /home/deploy/backups/backup.log 2>&1
```

### Восстановление из дампа

```bash
# Остановить API и воркеры
docker compose -f infra/docker-compose.cpu.yml stop api celery_worker celery_beat bot

# Восстановить БД
gunzip -c /home/deploy/backups/postgres/clips_2026-03-01_03-00.sql.gz | \
  docker compose -f infra/docker-compose.cpu.yml exec -T postgres \
  psql -U clips clips

# Запустить обратно
docker compose -f infra/docker-compose.cpu.yml start api celery_worker celery_beat bot
```

---

## 16. Расписание pipeline

Все задачи работают по московскому времени (`Europe/Moscow`):

| Время МСК | Задача | Описание |
|---|---|---|
| 08:00 | `task_search_candidates` | Поиск видео на YouTube по тематикам, отправка в Telegram |
| 11:00 | `task_download_approved` | Скачать одобренные видео, извлечь аудио FLAC, загрузить в S3 |
| 14:00 | `task_start_gpu_pod` | CPU запускает Vast.ai GPU-инстанс |
| ~15:00 | GPU работает | WhisperX транскрибирует аудио (1 задача за раз) |
| 01:00 | `task_run_llm_analysis` | GPT-4o-mini выбирает хайлайты из транскрипта |
| 04:00 | `task_render_clips_batch` | ffmpeg нарезает клипы на CPU |
| 06:00 | `task_send_daily_notification` | Telegram-уведомление «клипы готовы» |
| Каждые 15 мин | `task_reaper` | Возвращает зависшие GPU-задачи в очередь |

GPU-воркер **автоматически выключается** через 60 секунд после завершения последней задачи.

---

## Частые проблемы

### API не отвечает

```bash
docker compose -f infra/docker-compose.cpu.yml logs api --tail=50
# Проверить переменные окружения:
docker compose -f infra/docker-compose.cpu.yml exec api env | grep DATABASE_URL
```

### Ошибка подключения к PostgreSQL

```bash
# Проверить что postgres запущен и healthy
docker compose -f infra/docker-compose.cpu.yml ps postgres
# Проверить пароль (должен совпадать в .env и docker-compose.yml)
```

### Celery задачи не запускаются

```bash
docker compose -f infra/docker-compose.cpu.yml logs celery_worker --tail=50
docker compose -f infra/docker-compose.cpu.yml logs celery_beat --tail=20
# Проверить Redis:
docker compose -f infra/docker-compose.cpu.yml exec redis redis-cli ping
```

### CORS ошибки на фронтенде

Проверь в `cpu-backend.env`:
```bash
FRONTEND_ORIGIN=https://your-domain.com  # без trailing slash
ENV=production
```

Перезапусти API после изменения:
```bash
docker compose -f infra/docker-compose.cpu.yml restart api
```

### Telegram бот не отвечает

```bash
docker compose -f infra/docker-compose.cpu.yml logs bot --tail=30
# Проверить токен:
curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe
```

### S3 ошибки при загрузке

```bash
# Проверить доступность S3
docker compose -f infra/docker-compose.cpu.yml exec api python3 -c "
import boto3
from app.core.config import settings
s3 = boto3.client('s3',
  endpoint_url=settings.S3_ENDPOINT_URL,
  aws_access_key_id=settings.S3_ACCESS_KEY,
  aws_secret_access_key=settings.S3_SECRET_KEY,
)
print(s3.list_buckets())
"
```
