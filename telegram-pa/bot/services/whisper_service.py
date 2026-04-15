import asyncio
import os
import tempfile
from pathlib import Path

from openai import OpenAI
from pydub import AudioSegment

from bot.config import OPENAI_API_KEY, AUDIO_CHUNK_MINUTES, WHISPER_MAX_BYTES

_client = OpenAI(api_key=OPENAI_API_KEY)


def _convert_to_mp3(input_path: str) -> str:
    out_path = input_path.rsplit(".", 1)[0] + ".mp3"
    audio = AudioSegment.from_file(input_path)
    audio.export(out_path, format="mp3", bitrate="64k")
    return out_path


def _transcribe_file(mp3_path: str) -> str:
    with open(mp3_path, "rb") as f:
        result = _client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return result


def _chunk_and_transcribe(mp3_path: str) -> str:
    audio = AudioSegment.from_mp3(mp3_path)
    chunk_ms = AUDIO_CHUNK_MINUTES * 60 * 1000
    chunks = [audio[i : i + chunk_ms] for i in range(0, len(audio), chunk_ms)]

    transcripts: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmpdir, f"chunk_{idx}.mp3")
            chunk.export(chunk_path, format="mp3", bitrate="64k")
            transcripts.append(_transcribe_file(chunk_path))

    return "\n".join(transcripts)


def _transcribe_sync(audio_path: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy to temp dir to work with
        import shutil
        tmp_input = os.path.join(tmpdir, Path(audio_path).name)
        shutil.copy2(audio_path, tmp_input)

        mp3_path = _convert_to_mp3(tmp_input)

        if os.path.getsize(mp3_path) > WHISPER_MAX_BYTES:
            return _chunk_and_transcribe(mp3_path)
        return _transcribe_file(mp3_path)


async def transcribe(audio_path: str) -> str:
    return await asyncio.to_thread(_transcribe_sync, audio_path)
