"""Transcribe audio with OpenAI Whisper API (whisper-1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from openai import APIConnectionError, APIError, OpenAI, RateLimitError as OpenAIRateLimitError

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # OpenAI Whisper limit


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def _check_size(num_bytes: int) -> None:
    if num_bytes > MAX_AUDIO_BYTES:
        raise ValueError(
            f"Audio exceeds Whisper limit ({MAX_AUDIO_BYTES // (1024 * 1024)}MB max); got {num_bytes / (1024 * 1024):.2f}MB."
        )


def _transcribe_file_object(
    *,
    file_obj: BinaryIO,
    filename: str,
    language: str | None = None,
) -> str:
    client = _get_client()
    try:
        file_obj.seek(0)
    except (OSError, AttributeError):
        pass

    if not getattr(file_obj, "name", None):
        try:
            file_obj.name = filename  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            pass

    try:
        kwargs: dict = {"model": "whisper-1", "file": (filename, file_obj)}
        if language:
            kwargs["language"] = language
        result = client.audio.transcriptions.create(**kwargs)
    except (APIConnectionError, OpenAIRateLimitError, APIError) as e:
        raise RuntimeError(f"OpenAI Whisper API error: {e}") from e

    text = (getattr(result, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Whisper returned an empty transcript.")
    return text


def transcribe_audio_file(
    audio_path: str | Path,
    *,
    language: str | None = None,
) -> str:
    """
    Transcribe audio from a file path using Whisper (``whisper-1``).

    Enforces a 25MB maximum file size (OpenAI limit).

    Raises:
        ValueError: missing API key or file too large
        FileNotFoundError: path does not exist
        RuntimeError: API errors or empty transcript
    """
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    size = path.stat().st_size
    _check_size(size)

    with path.open("rb") as f:
        return _transcribe_file_object(file_obj=f, filename=path.name, language=language)


def transcribe_audio(
    *,
    audio_file: BinaryIO,
    filename: str = "audio.mp3",
    language: str | None = None,
) -> str:
    """
    Transcribe from a binary stream (e.g. Streamlit upload). Same 25MB limit when size is known.
    """
    try:
        pos = audio_file.tell()
    except (OSError, AttributeError):
        pass
    else:
        try:
            audio_file.seek(0, 2)
            n = audio_file.tell() - pos
            audio_file.seek(pos)
            _check_size(int(n))
        except (OSError, AttributeError):
            pass

    try:
        data = audio_file.read()
        if data:
            _check_size(len(data))
    except (OSError, AttributeError, TypeError):
        pass
    finally:
        try:
            audio_file.seek(0)
        except (OSError, AttributeError):
            pass

    return _transcribe_file_object(file_obj=audio_file, filename=filename, language=language)
