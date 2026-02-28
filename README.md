# Транскрипция видео (WhisperX + yt-dlp)

Production-ready скрипт для офлайн-транскрипции видео: скачивание по ссылке, извлечение аудио, распознавание речи Whisper large-v3 и выравнивание по словам через WhisperX. На выходе — полный текст (.txt), JSON со словами и таймкодами, субтитры (.srt). Работает на CPU и GPU (CUDA), без платных API и облачных сервисов.

## Требования

- **Python 3.10+**
- **FFmpeg** — должен быть установлен в системе и доступен в PATH
- Достаточно места на диске для моделей Whisper large-v3 и alignment (несколько ГБ при первом запуске)

## Установка

### 1. Клонирование / копирование проекта

Скопируйте в рабочую директорию файлы:
- `transcribe_video.py`
- `requirements.txt`

### 2. Виртуальное окружение (рекомендуется)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
```

### 3. Зависимости Python

```bash
pip install -r requirements.txt
```

Для **CPU-only** (без CUDA) можно установить PyTorch с официального зеркала:

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install whisperx yt-dlp
```

### 4. FFmpeg

Установите FFmpeg и добавьте его в PATH.

- **Windows**: [скачать](https://www.gyan.dev/ffmpeg/builds/) или через пакетный менеджер:
  - `winget install FFmpeg`
  - или Chocolatey: `choco install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Debian/Ubuntu), `sudo dnf install ffmpeg` (Fedora) и т.п.
- **macOS**: `brew install ffmpeg`

Проверка:

```bash
ffmpeg -version
```

## Использование

### Базовый запуск

```bash
python transcribe_video.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

По умолчанию выходные файлы создаются в папке `output/`.

### Параметры

| Параметр | Описание |
|----------|----------|
| `url` | Ссылка на видео (обязательный аргумент). Поддерживаются YouTube, Instagram, TikTok, прямые ссылки на mp4 и др. |
| `--output-dir` | Директория для результатов и временных файлов (по умолчанию: `output`) |
| `--model-dir` | Директория кэша моделей Whisper/WhisperX (по умолчанию — стандартный кэш) |
| `--language` | Код языка (например `en`, `ru`). Если не указан — автоопределение |
| `--keep-temp` | Не удалять скачанное видео и временный WAV после успешного завершения |
| `--verbose` | Подробный вывод (уровень DEBUG) |

### Примеры

```bash
# Выход в текущую папку (в подпапку output)
python transcribe_video.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Указать свою папку и язык
python transcribe_video.py "https://www.instagram.com/reel/..." --output-dir ./results --language ru

# Сохранить временные файлы для отладки
python transcribe_video.py "https://example.com/video.mp4" --keep-temp --verbose
```

### Выходные файлы

В указанной `--output-dir` создаются:

- **`<имя>_words.json`** — список слов с таймкодами: `[{"word": "...", "start": 0.0, "end": 0.5}, ...]`
- **`<имя>.txt`** — полный текст транскрипции
- **`<имя>.srt`** — субтитры в формате SRT

После успешного завершения скачанное видео и временный WAV удаляются (если не указан `--keep-temp`).

## Поведение

1. Проверяются зависимости (ffmpeg, torch, whisperx, yt-dlp) и наличие CUDA.
2. Видео скачивается через yt-dlp во временную директорию (внутри `--output-dir`).
3. FFmpeg извлекает аудио в формат 16 kHz, mono, WAV.
4. Загружается модель Whisper large-v3, выполняется транскрипция.
5. Загружается модель выравнивания для определённого языка, выполняется word-level alignment.
6. Результаты сохраняются в .txt, .json и .srt.
7. При успехе удаляются исходное видео и временный WAV (если не задан `--keep-temp`).

При невалидной ссылке или ошибке сети скрипт логирует сообщение и завершается с кодом 1, без падения с трассой.

## Лицензия и использование

Используются открытые компоненты: yt-dlp, FFmpeg, Whisper (OpenAI), WhisperX, PyTorch. Платные API и облачные сервисы не используются.
