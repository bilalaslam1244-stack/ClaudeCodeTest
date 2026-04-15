import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import whisper_service


async def download_and_transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Download a voice/audio message from Telegram and return its transcript."""
    message = update.effective_message

    if message.voice:
        tg_file = await context.bot.get_file(message.voice.file_id)
        suffix = ".ogg"
    elif message.audio:
        tg_file = await context.bot.get_file(message.audio.file_id)
        suffix = os.path.splitext(message.audio.file_name or ".ogg")[1] or ".ogg"
    elif message.document:
        tg_file = await context.bot.get_file(message.document.file_id)
        suffix = os.path.splitext(message.document.file_name or ".ogg")[1] or ".ogg"
    else:
        raise ValueError("No audio content found in message")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        transcript = await whisper_service.transcribe(tmp_path)
        return transcript
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
