import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import doc_service, whisper_service, memory_service
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


_VISION_BATCH_SIZE = 5   # pages per Claude Haiku vision call (last-resort only)
_MIN_TEXT_CHARS = 200    # threshold to consider text extraction successful


def _extract_pdf_text(path: str) -> str:
    """Try PyMuPDF then pdfplumber to extract text from a text-layer PDF."""
    # Method 1: PyMuPDF
    try:
        import fitz
        doc = fitz.open(path)
        text = "\n\n".join(page.get_text() for page in doc).strip()
        doc.close()
        if len(text) >= _MIN_TEXT_CHARS:
            return text
    except Exception:
        pass

    # Method 2: pdfplumber (sometimes succeeds where PyMuPDF misses)
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            parts = [p.extract_text() or "" for p in pdf.pages]
        text = "\n\n".join(parts).strip()
        if len(text) >= _MIN_TEXT_CHARS:
            return text
    except Exception:
        pass

    return ""


def _pdf_page_count(path: str) -> int:
    try:
        import fitz
        doc = fitz.open(path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0


def _ocr_pdf_tesseract(path: str) -> str:
    """OCR every page with local Tesseract — free, fast, no API cost."""
    import fitz
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        return ""

    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for OCR accuracy
    doc = fitz.open(path)
    pages_text = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="eng+chi_sim+msa",
                                           config="--psm 3")
        if text.strip():
            pages_text.append(text)
    doc.close()
    return "\n\n".join(pages_text).strip()


def _pdf_pages_to_images_b64(path: str, start: int, end: int) -> list[str]:
    """Render a page range to base64 PNG for Claude vision (last resort)."""
    import base64
    import fitz
    mat = fitz.Matrix(1.0, 1.0)  # 1x — lower cost, still readable
    doc = fitz.open(path)
    images = []
    for i in range(start, min(end, doc.page_count)):
        pix = doc[i].get_pixmap(matrix=mat)
        images.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    doc.close()
    return images


async def _handle_raw_file(update, context, tmp_path: str, file_name: str, caption: str) -> None:
    """Read an uploaded file into memory and ask the user what to do with it."""
    from bot.services import claude_service

    ext = os.path.splitext(file_name)[1].lower()
    raw_content = ""

    if ext == ".pdf":
        await update.effective_message.reply_text("Reading your PDF...")
        raw_content = await asyncio.to_thread(_extract_pdf_text, tmp_path)

        if not raw_content:
            total_pages = await asyncio.to_thread(_pdf_page_count, tmp_path)
            if total_pages == 0:
                await update.effective_message.reply_text(
                    "Couldn't read this PDF. Try exporting with a text layer or paste the content directly."
                )
                return

            # Try Tesseract OCR first — free, local, fast (~1-2s/page)
            await update.effective_message.reply_text(
                f"Scanned PDF ({total_pages} pages) — running OCR locally, won't take long..."
            )
            raw_content = await asyncio.to_thread(_ocr_pdf_tesseract, tmp_path)

            if not raw_content:
                # Tesseract not installed or failed — fall back to Claude Haiku vision
                await update.effective_message.reply_text(
                    "Local OCR unavailable — using vision analysis (this will take a few minutes)..."
                )
                system = (
                    "Extract ALL text, figures, tables, and data from these pages verbatim. "
                    "Preserve numbers, names, dates, and structure exactly. Do not summarise."
                )
                from bot.config import CLAUDE_HAIKU_MODEL
                extracted_parts = []
                try:
                    for batch_start in range(0, total_pages, _VISION_BATCH_SIZE):
                        batch_end = min(batch_start + _VISION_BATCH_SIZE, total_pages)
                        images = await asyncio.to_thread(
                            _pdf_pages_to_images_b64, tmp_path, batch_start, batch_end
                        )
                        if not images:
                            continue
                        batch_label = f"pages {batch_start + 1}–{batch_end}"
                        part = await asyncio.to_thread(
                            claude_service.chat_with_vision,
                            system,
                            f"Extract all content from {batch_label} of '{file_name}'.",
                            images,
                            CLAUDE_HAIKU_MODEL,
                        )
                        extracted_parts.append(f"--- {batch_label} ---\n{part}")
                except Exception as exc:
                    logger.error("Vision analysis failed: %s", exc)
                    await update.effective_message.reply_text(
                        "Vision analysis failed. Try exporting the PDF with a text layer."
                    )
                    return
                raw_content = "\n\n".join(extracted_parts)
    else:
        try:
            with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read(20000)
        except Exception:
            await update.effective_message.reply_text(
                "Can't read this file type. Please send a PDF, .txt, or .csv."
            )
            return

    if not raw_content.strip():
        await update.effective_message.reply_text("The file appears to be empty.")
        return

    # Store document content in conversation memory (truncated to 5000 chars)
    content_for_memory = raw_content[:5000] + ("\n...[content truncated]" if len(raw_content) > 5000 else "")
    doc_memory_entry = f"[DOCUMENT: {file_name}]\n{content_for_memory}"
    if caption:
        doc_memory_entry = f"[DOCUMENT: {file_name}] (user note: {caption})\n{content_for_memory}"

    await memory_service.add_message("user", doc_memory_entry)

    # Ask what to do — don't act yet
    reply = (
        f"Got it, I've read {file_name}. What would you like me to do with it?\n\n"
        "I can: answer questions about it, summarise it, extract specific info, "
        "generate a report or one-pager, or anything else — just say the word."
    )
    await update.effective_message.reply_text(reply)
    await memory_service.add_message("assistant", reply)
