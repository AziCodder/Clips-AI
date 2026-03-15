# Cookies для YouTube (yt-dlp)

Если при добавлении ссылки на YouTube появляется ошибка **«Sign in to confirm you're not a bot»**, YouTube требует авторизацию. Нужно передать yt-dlp файл с cookies из браузера.

## 1. Экспорт cookies в браузере

### Chrome / Edge / Firefox

1. Установите расширение для экспорта cookies в формате Netscape, например:
   - [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome)
   - [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox)
2. Откройте **youtube.com** и при необходимости войдите в аккаунт.
3. Экспортируйте cookies для текущего сайта в файл (формат **Netscape** / `.txt`).

### Альтернатива: yt-dlp с браузером (на своей машине)

Если yt-dlp установлен локально и есть браузер Chrome:

```bash
yt-dlp --cookies-from-browser chrome "https://www.youtube.com/watch?v=VIDEO_ID" --print-json
```

Для использования на сервере всё равно нужен файл cookies (см. ниже).

## 2. Размещение файла на сервере

- Создайте папку для cookies (например `infra/env/cookies/`).
- Загрузите экспортированный файл на сервер, например как:
  - `infra/env/cookies/youtube_cookies.txt`

**Важно:** эта папка добавлена в `.gitignore` — не коммитьте файл с cookies в репозиторий.

## 3. Настройка приложения

### Вариант A: Docker Compose (рекомендуется)

В `infra/docker-compose.cpu.yml` для сервисов **api** и **celery_worker** уже задан путь к cookies и смонтирована папка `infra/env/cookies/`. Достаточно:

1. Положить экспортированный файл сюда:
   - **infra/env/cookies/youtube_cookies.txt**
2. Перезапустить контейнеры:
   ```bash
   cd infra
   docker compose -f docker-compose.cpu.yml up -d api celery_worker
   ```
   (Переменная `YTDLP_COOKIES_FILE` уже прописана в compose; при необходимости её можно переопределить в `infra/env/cpu-backend.env`.)

### Вариант B: Без Docker

В `.env` (или в переменных окружения) задайте путь к файлу:

```env
YTDLP_COOKIES_FILE=/полный/путь/к/youtube_cookies.txt
```

Перезапустите API и воркеры Celery.

## 4. Проверка на сервере

Убедитесь, что файл есть на хосте и виден внутри контейнера:

```bash
# Из корня проекта (~/clips)
ls -la infra/env/cookies/youtube_cookies.txt

# Файл должен быть виден в контейнере api по пути /workspace/cookies/
docker compose -f infra/docker-compose.cpu.yml exec api ls -la /workspace/cookies/
docker compose -f infra/docker-compose.cpu.yml exec api cat /workspace/cookies/youtube_cookies.txt | head -5
```

Если `ls /workspace/cookies/` пустой или файла нет — проверьте, что в `docker-compose.cpu.yml` у сервисов **api** и **celery_worker** есть volume `./env/cookies:/workspace/cookies` (без `:ro`: yt-dlp при выходе сохраняет cookies в этот файл) и переменная `YTDLP_COOKIES_FILE=/workspace/cookies/youtube_cookies.txt`. Запускайте compose из каталога **infra** (`cd infra && docker compose -f docker-compose.cpu.yml ...`), чтобы путь `./env/cookies` указывал на `infra/env/cookies`.

## 5. Проверка добавления видео

Добавьте вручную ту же ссылку на видео ещё раз. Если cookies подхватились, ошибка «Sign in to confirm» исчезнет и видео будет добавлено.

## 6. Обновление cookies

Cookies со временем истекают. Если снова появится ошибка входа — повторите экспорт из браузера и замените файл на сервере, затем перезапустите сервисы.

## Ссылки

- [yt-dlp: как передать cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
- [Экспорт cookies для YouTube](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
