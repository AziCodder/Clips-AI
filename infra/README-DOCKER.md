# Запуск проекта через Docker

Запуск из **корня репозитория**:

```powershell
cd "D:\темки\Бизнес Проекта\CLIP AI\Автоматизация 2"
docker compose -f infra/docker-compose.cpu.yml up -d --build
```

После первого запуска выполните миграции БД:

```powershell
docker compose -f infra/docker-compose.cpu.yml exec api alembic -c alembic.ini upgrade head
```

## Сервисы

| Сервис         | Порт  | Описание                    |
|----------------|-------|-----------------------------|
| Frontend       | 80    | http://localhost            |
| API            | 8000  | http://localhost:8000/api/docs |
| PostgreSQL     | 5432  | clips / clips / clips        |
| Redis          | 6379  |                             |

## Переменные окружения

Файл `infra/env/cpu-backend.env` — подставьте свои ключи (Telegram, S3, OpenAI и т.д.) при необходимости. Для локальной проверки достаточно значений по умолчанию (LLM_USE_MOCK и заглушки).

## Остановка

```powershell
docker compose -f infra/docker-compose.cpu.yml down
```

Данные БД и Redis сохраняются в томах Docker.

---

## Как проверить удаление видео

1. **Запустите проект** (из корня репозитория):

   ```powershell
   cd "D:\темки\Бизнес Проекта\CLIP AI\Автоматизация 2"
   docker compose -f infra/docker-compose.cpu.yml up -d --build
   ```

2. **При первом запуске выполните миграции:**

   ```powershell
   docker compose -f infra/docker-compose.cpu.yml exec api alembic -c alembic.ini upgrade head
   ```

3. **Откройте в браузере:** [http://localhost:8000](http://localhost:8000)

4. **Войдите** (Регистрация / Вход), если ещё не авторизованы.

5. **Перейдите в раздел «Видео»** — на каждой карточке справа сверху должна быть кнопка с **тремя точками**.

6. **Нажмите на три точки** → откроется меню:
   - **«Удалить всё»** — удаляет видео и всё связанное (нарезки, тексты, ассеты в S3).
   - **«Удалить видео»** — удаляет только полный текст, описание и транскрипты; нарезки (клипы) остаются.

7. После удаления список обновится автоматически.

**Проверка API напрямую:** [http://localhost:8001/docs](http://localhost:8001/docs) — там можно вызвать `DELETE /api/v1/videos/{video_id}?scope=all` или `?scope=video_only`.
