import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import doc_service, whisper_service
from bot.utils.formatting import send_long_message
from bot.utils.file_utils import cleanup


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded documents — raw files for report generation or meeting audio."""
    message = update.effective_message
    doc = message.document

    if doc is None:
        return

    file_name = doc.file_name or "upload"
    ext = os.path.splitext(file_name)[1].lower()
    audio_exts = {".ogg", ".mp3", ".m4a", ".wav", ".mp4", ".mpeg", ".mpga", ".webm", ".caf"}

    tg_file = await context.bot.get_file(doc.file_id)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        if ext in audio_exts:
            # Meeting minutes flow
            await update.effective_message.reply_text(
                "Transcribing audio... this may take a moment."
            )
            transcript = await whisper_service.transcribe(tmp_path)
            await update.effective_message.reply_text(
                "Generating meeting minutes..."
            )
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
            # Raw text/data file — read content and generate report
            try:
                with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                    raw_content = f.read(20000)  # cap at 20k chars
            except Exception:
                await update.effective_message.reply_text(
                    "Could not read the file. Please send a text-based file."
                )
                return

            caption = message.caption or ""
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

    finally:
        cleanup(tmp_path)
