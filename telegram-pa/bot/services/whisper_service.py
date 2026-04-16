import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from openai import OpenAI
from pydub import AudioSegment

from bot.config import OPENAI_API_KEY, AUDIO_CHUNK_MINUTES, WHISPER_MAX_BYTES

_client = OpenAI(api_key=OPENAI_API_KEY)

# Audio shorter than this is treated as a voice command, longer as a meeting recording
MEETING_THRESHOLD_SECONDS = 60


def get_audio_duration_seconds(audio_path: str) -> float:
    audio = AudioSegment.from_file(audio_path)
    return len(audio) / 1000.0


def is_meeting_length(audio_path: str) -> bool:
    try:
        return get_audio_duration_seconds(audio_path) >= MEETING_THRESHOLD_SECONDS
    except Exception:
        return False


def _convert_to_mp3(input_path: str) -> str:
    out_path = input_path.rsplit(".", 1)[0] + ".mp3"
    audio = AudioSegment.from_file(input_path)
    audio.export(out_path, format="mp3", bitrate="64k")
    return out_path


def _transcribe_file(mp3_path: str, language: str | None = None) -> str:
    with open(mp3_path, "rb") as f:
        kwargs = dict(model="whisper-1", file=f, response_format="text")
        if language:
            kwargs["language"] = language
        result = _client.audio.transcriptions.create(**kwargs)
    return result


def _chunk_and_transcribe(mp3_path: str, language: str | None = None) -> str:
    audio = AudioSegment.from_mp3(mp3_path)
    chunk_ms = AUDIO_CHUNK_MINUTES * 60 * 1000
    chunks = [audio[i : i + chunk_ms] for i in range(0, len(audio), chunk_ms)]

    transcripts: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmpdir, f"chunk_{idx}.mp3")
            chunk.export(chunk_path, format="mp3", bitrate="64k")
            transcripts.append(_transcribe_file(chunk_path, language=language))

    return "\n".join(transcripts)


def _transcribe_sync(audio_path: str, language: str | None = None) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_input = os.path.join(tmpdir, Path(audio_path).name)
        shutil.copy2(audio_path, tmp_input)

        mp3_path = _convert_to_mp3(tmp_input)

        if os.path.getsize(mp3_path) > WHISPER_MAX_BYTES:
            return _chunk_and_transcribe(mp3_path, language=language)
        return _transcribe_file(mp3_path, language=language)


def _pick_whisper_language(lang: str) -> str | None:
    """Return Whisper language code. Force 'en' for non-Chinese input."""
    if lang == "zh-cn":
        return "zh"
    return "en"


async def transcribe(audio_path: str, lang: str = "en") -> str:
    whisper_lang = _pick_whisper_language(lang)
    return await asyncio.to_thread(_transcribe_sync, audio_path, language=whisper_lang)
