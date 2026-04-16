import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import doc_service, whisper_service
from bot.utils.formatting import send_long_message
from bot.utils.file_utils import cleanup

_AUDIO_EXTS = {".ogg", ".mp3", ".m4a", ".wav", ".mp4", ".mpeg", ".mpga", ".webm", ".caf", ".aac"}


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded documents and audio files."""
    message = update.effective_message

    if message.document:
        media = message.document
        file_name = media.file_name or "upload"
    elif message.audio:
        media = message.audio
        file_name = media.file_name or (media.title or "audio") + ".m4a"
    else:
        return

    ext = os.path.splitext(file_name)[1].lower() or ".m4a"
    tg_file = await context.bot.get_file(media.file_id)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        if ext in _AUDIO_EXTS:
            await _handle_audio(update, context, tmp_path, file_name)
        else:
            await _handle_raw_file(update, context, tmp_path, file_name, message.caption or "")

    finally:
        cleanup(tmp_path)


async def _handle_audio(update, context, tmp_path: str, file_name: str) -> None:
    """Route based on duration: long = meeting minutes, short = voice command."""
    is_meeting = whisper_service.is_meeting_length(tmp_path)

    if is_meeting:
        await update.effective_message.reply_text(
            "Meeting recording detected. Transcribing... this may take a moment."
        )
        transcript = await whisper_service.transcribe(tmp_path, lang="en")
        await update.effective_message.reply_text("Generating meeting minutes...")
        minutes_content = await doc_service.generate_meeting_minutes(transcript)
        title = f"Meeting Minutes — {file_name}"
        doc_path = await doc_service.create_document(minutes_content, title, fmt="docx")
        try:
            with open(doc_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=os.path.basename(doc_path),
                    caption="Meeting minutes ready.",
                )
        finally:
            cleanup(doc_path)
    else:
        # Short audio — treat as a voice command, route back through message_handler
        from bot.handlers.message_handler import handle_message
        await handle_message(update, context, audio_path_override=tmp_path)


async def _handle_raw_file(update, context, tmp_path: str, file_name: str, caption: str) -> None:
    """Generate a report from an uploaded text/data file."""
    try:
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            raw_content = f.read(20000)
    except Exception:
        await update.effective_message.reply_text(
            "Could not read the file. Please send a text-based file."
        )
        return

    prompt = (
        f"The user uploaded a file named '{file_name}'"
        + (f" with note: {caption}" if caption else "")
        + f"\n\nFile contents:\n{raw_content}\n\n"
        "Generate a professional report or summary based on this content."
    )
    await update.effective_message.reply_text("Generating document...")
    content = await doc_service.generate_content(prompt)
    doc_path = await doc_service.create_document(content, file_name, fmt="docx")
    try:
        with open(doc_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=os.path.basename(doc_path),
                caption="Document ready.",
            )
    finally:
        cleanup(doc_path)
