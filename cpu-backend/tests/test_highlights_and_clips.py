"""
Тесты пайплайна: ИИ подбор лучших моментов по транскрипту + нарезка клипов из видео.

Запуск:
  cd cpu-backend
  pip install -r requirements-dev.txt
  pip install -r requirements.txt   # для юнит- и интеграционного теста
  pytest tests/test_highlights_and_clips.py -v

Интеграционный тест (реальные файлы):
  Задайте пути к своему транскрипту и видео через переменные окружения,
  затем запустите с маркером integration:

  set TEST_TEXT_PATH=<путь к transcript.txt>
  set TEST_VIDEO_PATH=<путь к video.mp4>
  set TEST_OUTPUT_DIR=<папка для клипов>
  pytest tests/test_highlights_and_clips.py -v -m integration

  Без этих переменных интеграционный тест пропускается.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def temp_transcript():
    """Временный файл с транскриптом (как от WhisperX)."""
    content = """
Привет, это тестовый транскрипт для проверки нарезки.
В нём есть несколько предложений.
ИИ должен выбрать лучшие моменты по этому тексту.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(content.strip())
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def temp_output_dir():
    """Временная папка для клипов."""
    with tempfile.TemporaryDirectory() as d:
        yield d


class FakeHighlight:
    def __init__(self, start_sec: float, end_sec: float, score: float = 0.9, title: str = "", reason: str = ""):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.score = score
        self.title = title
        self.reason = reason


def test_run_highlights_and_clips_from_files_unit(
    temp_transcript: str,
    temp_output_dir: str,
) -> None:
    """
    Юнит-тест: с подменой ИИ и ffmpeg проверяем, что runner читает текст,
    вызывает ИИ и нарезку с правильными аргументами.
    Требует установленных зависимостей: pip install -r requirements.txt
    """
    try:
        from app.services.llm import provider  # noqa: F401
    except ImportError as e:
        pytest.skip(f"Нужны зависимости бэкенда (pip install -r requirements.txt): {e}")

    fake_video = os.path.join(temp_output_dir, "fake_video.mp4")
    # Создаём пустой файл «видео», чтобы проверка os.path.isfile прошла
    with open(fake_video, "wb") as f:
        f.write(b"\x00\x00\x00\x00")

    fake_highlights = [
        FakeHighlight(0.0, 20.0, 0.95, "Первый момент", "Важно"),
        FakeHighlight(30.0, 55.0, 0.85, "Второй момент", "Эмоционально"),
    ]

    async def fake_extract(transcript: str, prompt: str, clips_count: int):
        assert transcript.strip()
        assert clips_count == 3
        return fake_highlights

    fake_provider = MagicMock()
    fake_provider.extract_highlights = fake_extract

    cut_clip_calls: list[tuple] = []

    def fake_cut_clip(video_path: str, start_sec: float, end_sec: float, output_path: str, **kwargs) -> str:
        cut_clip_calls.append((video_path, start_sec, end_sec, output_path))
        # Создаём пустой «клип», чтобы код не упал на проверке файла
        with open(output_path, "wb") as f:
            f.write(b"fake clip")
        return output_path

    with (
        patch("app.services.llm.provider.get_llm_provider", return_value=fake_provider),
        patch("app.services.ffmpeg_service.cut_clip", side_effect=fake_cut_clip),
    ):
        from app.services.highlights_runner import run_highlights_and_clips_from_files

        result = run_highlights_and_clips_from_files(
            temp_transcript,
            fake_video,
            temp_output_dir,
            prompt="Выбери лучшие моменты",
            clips_count=3,
        )

    assert len(result) == 2
    assert len(cut_clip_calls) == 2
    assert cut_clip_calls[0][0] == fake_video
    assert cut_clip_calls[0][1] == 0.0
    assert cut_clip_calls[0][2] == 20.0
    assert cut_clip_calls[0][3].endswith("clip_1.mp4")
    assert cut_clip_calls[1][1] == 30.0
    assert cut_clip_calls[1][2] == 55.0
    assert cut_clip_calls[1][3].endswith("clip_2.mp4")

    assert os.path.isfile(os.path.join(temp_output_dir, "clip_1.mp4"))
    assert os.path.isfile(os.path.join(temp_output_dir, "clip_2.mp4"))


def test_run_raises_on_missing_text_file(temp_output_dir: str) -> None:
    """Ожидаемое исключение при отсутствии файла транскрипта."""
    from app.services.highlights_runner import run_highlights_and_clips_from_files

    fake_video = os.path.join(temp_output_dir, "video.mp4")
    with open(fake_video, "wb") as f:
        f.write(b"")

    with pytest.raises(FileNotFoundError, match="транскрипта"):
        run_highlights_and_clips_from_files(
            os.path.join(temp_output_dir, "nonexistent.txt"),
            fake_video,
            temp_output_dir,
        )


def test_run_raises_on_missing_video_file(temp_transcript: str, temp_output_dir: str) -> None:
    """Ожидаемое исключение при отсутствии файла видео."""
    from app.services.highlights_runner import run_highlights_and_clips_from_files

    with pytest.raises(FileNotFoundError, match="видео"):
        run_highlights_and_clips_from_files(
            temp_transcript,
            os.path.join(temp_output_dir, "no_video.mp4"),
            temp_output_dir,
        )


def test_run_raises_on_empty_transcript(temp_output_dir: str) -> None:
    """Ожидаемое исключение при пустом транскрипте."""
    empty_txt = os.path.join(temp_output_dir, "empty.txt")
    with open(empty_txt, "w", encoding="utf-8") as f:
        f.write("   \n\n  ")
    video_path = os.path.join(temp_output_dir, "v.mp4")
    with open(video_path, "wb") as f:
        f.write(b"")

    from app.services.highlights_runner import run_highlights_and_clips_from_files

    with pytest.raises(ValueError, match="пуст"):
        run_highlights_and_clips_from_files(empty_txt, video_path, temp_output_dir)


@pytest.mark.integration
def test_run_highlights_and_clips_integration(temp_output_dir: str) -> None:
    """
    Интеграционный тест: реальный ИИ (или Mock, если нет API ключа) и реальная нарезка ffmpeg.
    Запускается только если заданы TEST_TEXT_PATH и TEST_VIDEO_PATH.

    Пример:
      set TEST_TEXT_PATH=D:\\path\\to\\transcript.txt
      set TEST_VIDEO_PATH=D:\\path\\to\\video.mp4
      pytest tests/test_highlights_and_clips.py -v -m integration
    """
    text_path = os.environ.get("TEST_TEXT_PATH")
    video_path = os.environ.get("TEST_VIDEO_PATH")
    output_dir = os.environ.get("TEST_OUTPUT_DIR", temp_output_dir)

    if not text_path or not video_path:
        pytest.skip(
            "Задайте TEST_TEXT_PATH и TEST_VIDEO_PATH для интеграционного теста. "
            "Пример: set TEST_TEXT_PATH=D:\\data\\transcript.txt & set TEST_VIDEO_PATH=D:\\data\\video.mp4"
        )
    if not os.path.isfile(text_path):
        pytest.skip(f"Файл транскрипта не найден: {text_path}")
    if not os.path.isfile(video_path):
        pytest.skip(f"Файл видео не найден: {video_path}")

    from app.services.highlights_runner import run_highlights_and_clips_from_files

    result = run_highlights_and_clips_from_files(
        text_path,
        video_path,
        output_dir,
        prompt="Найди самые эмоциональные и ценные моменты для коротких клипов.",
        clips_count=3,
    )

    assert len(result) >= 1, "Должен получиться хотя бы один клип"
    for path in result:
        assert os.path.isfile(path), f"Клип не создан: {path}"
        assert os.path.getsize(path) > 0, f"Клип пустой: {path}"
