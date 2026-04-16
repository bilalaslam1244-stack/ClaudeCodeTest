import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import doc_service, whisper_service
from bot.utils.formatting import send_long_message
from bot.utils.file_utils import cleanup

logger = logging.getLogger(__name__)

_AUDIO_EXTS = {".ogg", ".mp3", ".m4a", ".wav", ".mp4", ".mpeg", ".mpga", ".webm", ".caf", ".aac"}
_MEETING_KEYWORDS = {"meeting", "minutes", "mom", "m.o.m", "transcript", "recording", "conference"}


def _caption_requests_meeting(caption: str) -> bool:
    low = caption.lower()
    return any(kw in low for kw in _MEETING_KEYWORDS)


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
            caption = message.caption or ""
            await _handle_audio(update, context, tmp_path, file_name, caption)
        else:
            await _handle_raw_file(update, context, tmp_path, file_name, message.caption or "")

    finally:
        cleanup(tmp_path)


async def _handle_audio(update, context, tmp_path: str, file_name: str, caption: str) -> None:
    """Route audio: caption with meeting keywords OR duration > 60 s → meeting minutes."""
    caption_wants_meeting = _caption_requests_meeting(caption)

    try:
        duration = whisper_service.get_audio_duration_seconds(tmp_path)
        is_long = duration >= 60
    except Exception as exc:
        logger.warning("Could not read audio duration (%s) — defaulting to meeting path", exc)
        is_long = True  # safe default: treat as meeting rather than silently failing

    treat_as_meeting = caption_wants_meeting or is_long

    if treat_as_meeting:
        await update.effective_message.reply_text(
            "Meeting recording detected. Transcribing... this may take a moment."
        )
        try:
            transcript = await whisper_service.transcribe(tmp_path, lang="en")
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            await update.effective_message.reply_text("Transcription failed. Please try again.")
            return

        await update.effective_message.reply_text("Generating meeting minutes document...")
        try:
            minutes_content = await doc_service.generate_meeting_minutes(transcript)
            title = "Meeting Minutes"
            doc_path = await doc_service.create_document(minutes_content, title, fmt="docx")
            with open(doc_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=os.path.basename(doc_path),
                    caption="Meeting minutes ready.",
                )
        except Exception as exc:
            logger.error("Minutes generation failed: %s", exc)
            await update.effective_message.reply_text(f"Could not generate minutes: {exc}")
        finally:
            try:
                cleanup(doc_path)
            except Exception:
                pass
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
