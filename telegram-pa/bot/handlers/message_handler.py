import logging
import re
from zoneinfo import ZoneInfo
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import ALLOWED_USER_ID, BOSS_TIMEZONE
from bot.handlers import voice_handler
from bot.services import (
    intent_router,
    claude_service,
    reminder_service,
    calendar_service,
    gmail_service,
    notes_service,
    doc_service,
    memory_service,
    url_service,
)
from bot.scheduler import jobs
from bot.utils.language import detect_language
from bot.utils.formatting import send_long_message, split_message, strip_markdown
from bot.utils.file_utils import cleanup

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.65
_URL_RE = re.compile(r"https?://\S+")
_KL_TZ = ZoneInfo(BOSS_TIMEZONE)


def _to_kl(iso: str) -> str:
    """Convert any ISO 8601 string to KL local time string for display."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        kl = dt.astimezone(_KL_TZ)
        return kl.strftime("%a, %d %b %Y %I:%M %p %Z")
    except Exception:
        return iso


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    audio_path_override: str | None = None,
) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else None

    if user_id != ALLOWED_USER_ID:
        return

    text = ""
    is_voice = False

    if audio_path_override:
        # Short audio forwarded from document_handler
        try:
            lang_hint = "en"
            text = await voice_handler.download_and_transcribe.__wrapped__ \
                if hasattr(voice_handler.download_and_transcribe, "__wrapped__") \
                else None
            # Transcribe directly from path
            from bot.services import whisper_service
            text = await whisper_service.transcribe(audio_path_override, lang="en")
            is_voice = True
            for part in split_message(f"[Transcript]\n{text}"):
                await message.reply_text(part)
        except Exception as exc:
            logger.error("Audio override transcription failed: %s", exc)
            await message.reply_text("Could not transcribe audio. Please try again.")
            return

    elif message.voice:
        try:
            # Download first so we can check duration before deciding what to do
            from bot.services import whisper_service as _ws
            from bot.utils.file_utils import cleanup as _cleanup
            tmp_voice_path = await voice_handler.download_audio_file(update, context)
            try:
                duration = _ws.get_audio_duration_seconds(tmp_voice_path)
            except Exception:
                duration = 0.0

            if duration >= 60:
                # Long voice note → meeting minutes doc
                await message.reply_text(
                    "Meeting recording detected. Transcribing... this may take a moment."
                )
                try:
                    transcript = await _ws.transcribe(tmp_voice_path, lang="en")
                    await message.reply_text("Generating meeting minutes document...")
                    minutes_content = await doc_service.generate_meeting_minutes(transcript)
                    doc_path = await doc_service.create_document(minutes_content, "Meeting Minutes", fmt="docx")
                    try:
                        with open(doc_path, "rb") as f:
                            await context.bot.send_document(
                                chat_id=update.effective_chat.id,
                                document=f,
                                filename="Meeting_Minutes.docx",
                                caption="Meeting minutes ready.",
                            )
                    finally:
                        _cleanup(doc_path)
                except Exception as exc:
                    logger.error("Voice meeting minutes failed: %s", exc)
                    await message.reply_text(f"Could not generate minutes: {exc}")
                finally:
                    _cleanup(tmp_voice_path)
                return
            else:
                # Short voice note → voice command
                await message.reply_text("Transcribing...")
                text = await _ws.transcribe(tmp_voice_path, lang="en")
                is_voice = True
                for part in split_message(f"[Transcript]\n{text}"):
                    await message.reply_text(part)
                _cleanup(tmp_voice_path)
        except Exception as exc:
            logger.error("Voice transcription failed: %s", exc)
            await message.reply_text("Could not transcribe the audio. Please try again.")
            return

    elif message.text:
        text = message.text.strip()
    else:
        return

    if not text:
        return

    # Memory clear — intercept before intent routing
    _clear_triggers = {"clear memory", "forget everything", "reset memory", "start fresh", "clear chat"}
    if text.lower().strip() in _clear_triggers or any(t in text.lower() for t in _clear_triggers):
        await memory_service.clear_history()
        await message.reply_text("Memory cleared. Starting fresh.")
        return

    # URL detection — intercept before intent routing
    url_match = _URL_RE.search(text)
    if url_match:
        url = url_match.group()
        lang = detect_language(text)
        await message.reply_text("Fetching and summarizing URL...")
        summary = await url_service.fetch_and_summarize(url, lang=lang)
        await send_long_message(context.bot, update.effective_chat.id, summary)
        # Store URL + full summary in memory so follow-up questions have context
        await memory_service.add_message("user", text)
        await memory_service.add_message(
            "assistant",
            f"[I fetched {url} and found the following]\n{summary}"
        )
        return

    lang = detect_language(text)
    tagged = f"[TRANSCRIPT] {text}" if is_voice else text

    # Save user message to memory
    await memory_service.add_message("user", text)

    result = intent_router.classify(tagged, lang)
    intent = result.intent
    entities = result.entities
    confidence = result.confidence

    logger.info("Intent: %s (%.2f) | lang: %s", intent, confidence, lang)

    if confidence < _CONFIDENCE_THRESHOLD:
        history = await memory_service.get_history()
        clarify = claude_service.chat_with_history(
            system=f"You are a helpful PA. The user said something ambiguous. "
                   f"Ask a short clarifying question in language: {lang}.",
            history=history,
            user=text,
        )
        await message.reply_text(clarify)
        await memory_service.add_message("assistant", clarify)
        return

    # ── Dispatch ──────────────────────────────────────────────────────────────

    if intent == "reminder_set":
        await _handle_reminder_set(update, context, entities, lang, text)

    elif intent == "reminder_list":
        await _handle_reminder_list(update, context, lang)

    elif intent == "reminder_cancel":
        await _handle_reminder_cancel(update, context, entities, lang, text)

    elif intent == "calendar_create":
        await _handle_calendar_create(update, context, entities, lang)

    elif intent == "calendar_reschedule":
        await _handle_calendar_reschedule(update, context, entities, lang, text)

    elif intent == "calendar_cancel":
        await _handle_calendar_cancel(update, context, entities, lang, text)

    elif intent == "calendar_list":
        await _handle_calendar_list(update, context, lang)

    elif intent == "note_save":
        await _handle_note_save(update, context, entities, lang, text)

    elif intent == "note_retrieve":
        await _handle_note_retrieve(update, context, entities, lang)

    elif intent in ("email_check", "email_summarize"):
        await _handle_email_check(update, context, entities, lang)

    elif intent == "email_overview":
        await _handle_email_overview(update, context, entities, lang)

    elif intent == "email_send":
        await _handle_email_send(update, context, entities, lang, text)

    elif intent == "doc_generate":
        await _handle_doc_generate(update, context, entities, lang, text)

    elif intent == "meeting_minutes":
        await message.reply_text(
            "Please send the meeting audio file as a file attachment (paperclip → File)."
        )

    else:
        await _handle_general_chat(update, context, lang, text)


# ── Intent handlers ────────────────────────────────────────────────────────────

async def _handle_reminder_set(update, context, entities, lang, original_text):
    time_iso = entities.get("time_iso")
    description = entities.get("description") or original_text

    if not time_iso:
        await update.effective_message.reply_text(
            "When should I remind you? Please specify a date and time."
        )
        return

    reminder = await reminder_service.create(description, time_iso)
    jobs.schedule_reminder(reminder)

    display_time = _to_kl(time_iso)
    reply = strip_markdown(claude_service.chat(
        system=f"Confirm a reminder was set. Be brief. Respond in language: {lang}.",
        user=f"Reminder: {description} at {display_time}",
    ))
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel reminder", callback_data=f"cancel_reminder:{reminder.job_id}")
    ]])
    await update.effective_message.reply_text(reply, reply_markup=keyboard)
    await memory_service.add_message("assistant", reply)


async def _handle_reminder_list(update, context, lang):
    reminders = await reminder_service.list_pending()
    if not reminders:
        reply = "No pending reminders."
        await update.effective_message.reply_text(reply)
        return

    lines = []
    keyboard_rows = []
    for r in reminders:
        display_time = _to_kl(r.remind_at)
        lines.append(f"• {display_time} — {r.description}")
        keyboard_rows.append([
            InlineKeyboardButton(
                f"Cancel: {r.description[:20]}",
                callback_data=f"cancel_reminder:{r.job_id}"
            )
        ])
    reply = "Pending reminders:\n" + "\n".join(lines)
    await update.effective_message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard_rows))


async def _handle_reminder_cancel(update, context, entities, lang, original_text):
    description = entities.get("description") or original_text
    reminders = await reminder_service.list_pending()
    if not reminders:
        await update.effective_message.reply_text("No pending reminders to cancel.")
        return

    options = "\n".join(f"{r.job_id}: {r.description}" for r in reminders)
    match_raw = claude_service.chat(
        system="Return only the job_id of the reminder that best matches the user's request. No other text.",
        user=f"User wants to cancel: {description}\nOptions:\n{options}",
        temperature=0.0,
        max_tokens=64,
    )
    job_id = match_raw.strip()
    cancelled = await reminder_service.cancel_by_job_id(job_id)
    try:
        jobs.get_scheduler().remove_job(job_id)
    except Exception:
        pass
    reply = "Reminder cancelled." if cancelled else "Could not find that reminder."
    await update.effective_message.reply_text(reply)


async def _handle_calendar_create(update, context, entities, lang):
    name = entities.get("calendar_event_name") or entities.get("description", "Meeting")
    time_iso = entities.get("time_iso")
    duration = entities.get("duration_minutes") or 60

    if not time_iso:
        await update.effective_message.reply_text("Please specify the date and time for the event.")
        return

    event = await calendar_service.create_event(name, time_iso, int(duration))
    display_time = _to_kl(time_iso)
    reply = strip_markdown(claude_service.chat(
        system=f"Confirm a calendar event was created. Be brief. Respond in language: {lang}.",
        user=f"Event '{name}' created at {display_time} for {duration} minutes.",
    ))
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel event", callback_data=f"cancel_event:{event['id']}")
    ]])
    await update.effective_message.reply_text(reply, reply_markup=keyboard)
    await memory_service.add_message("assistant", reply)


async def _handle_calendar_reschedule(update, context, entities, lang, original_text):
    name = entities.get("calendar_event_name") or entities.get("description", "")
    new_time = entities.get("time_iso")
    duration = int(entities.get("duration_minutes") or 60)

    event = await calendar_service.find_event_by_name(name)
    if not event:
        await update.effective_message.reply_text(f"No upcoming event found matching '{name}'.")
        return
    if not new_time:
        await update.effective_message.reply_text("Please specify the new date and time.")
        return

    await calendar_service.reschedule_event(event["id"], new_time, duration)
    display_time = _to_kl(new_time)
    reply = f"Rescheduled '{event.get('summary')}' to {display_time}."
    await update.effective_message.reply_text(reply)


async def _handle_calendar_cancel(update, context, entities, lang, original_text):
    name = entities.get("calendar_event_name") or entities.get("description", "")
    event = await calendar_service.find_event_by_name(name)
    if not event:
        await update.effective_message.reply_text(f"No upcoming event found matching '{name}'.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, cancel it", callback_data=f"cancel_event:{event['id']}"),
        InlineKeyboardButton("No, keep it", callback_data="noop"),
    ]])
    await update.effective_message.reply_text(
        f"Cancel '{event.get('summary')}'?", reply_markup=keyboard
    )


async def _handle_calendar_list(update, context, lang):
    events = await calendar_service.list_events(days_ahead=7)
    text = calendar_service.format_event_list(events)
    await send_long_message(context.bot, update.effective_chat.id, text)


async def _handle_note_save(update, context, entities, lang, text):
    topic = entities.get("topic")
    await notes_service.save(text, topic=topic, language=lang)
    reply = "Note saved." + (f" Topic: {topic}" if topic else "")
    await update.effective_message.reply_text(reply)


async def _handle_note_retrieve(update, context, entities, lang):
    keyword = entities.get("topic") or entities.get("description")
    notes = await notes_service.search(keyword=keyword)
    text = notes_service.format_notes(notes)
    await send_long_message(context.bot, update.effective_chat.id, text)


async def _handle_email_check(update, context, entities, lang):
    from_filter = entities.get("person") or entities.get("email_to")
    try:
        max_results = int(entities.get("count") or 10)
        max_results = max(1, min(max_results, 30))
    except (TypeError, ValueError):
        max_results = 10
    if from_filter:
        await update.effective_message.reply_text(f"Fetching emails from {from_filter}...")
    else:
        await update.effective_message.reply_text(f"Fetching and summarizing latest {max_results} email(s)...")
    digest = await gmail_service.get_emails_summary(max_results=max_results, from_filter=from_filter)
    await send_long_message(context.bot, update.effective_chat.id, digest)


async def _handle_email_overview(update, context, entities, lang):
    try:
        max_results = int(entities.get("count") or 10)
        max_results = max(1, min(max_results, 30))
    except (TypeError, ValueError):
        max_results = 10
    await update.effective_message.reply_text("Fetching inbox overview...")
    overview = await gmail_service.get_inbox_overview(max_results=max_results)
    await send_long_message(context.bot, update.effective_chat.id, overview)


_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")


async def _handle_email_send(update, context, entities, lang, text):
    to = entities.get("email_to")
    subject = entities.get("email_subject") or "Message from your PA"
    body = entities.get("email_body") or text

    if not to:
        await update.effective_message.reply_text(
            "Who should I send it to? Please provide an email address."
        )
        return

    # If 'to' is a name not an email address, look it up in Gmail history
    if not _EMAIL_RE.match(to.strip()):
        await update.effective_message.reply_text(f"Looking up email address for {to}...")
        resolved = await gmail_service.find_contact_email(to.strip())
        if resolved:
            to = resolved
        else:
            await update.effective_message.reply_text(
                f"Could not find an email address for '{to}'. "
                f"Please reply with their full email address."
            )
            return

    await update.effective_message.reply_text(f"Sending email to {to}...")
    try:
        await gmail_service.send_email(to=to, subject=subject, body=body)
        reply = f"Email sent to {to}."
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        await update.effective_message.reply_text(f"Failed to send email: {exc}")


async def _handle_doc_generate(update, context, entities, lang, text):
    fmt = entities.get("output_format") or "docx"
    if fmt not in ("docx", "pdf", "text"):
        fmt = "docx"

    await update.effective_message.reply_text("Generating document...")
    content = await doc_service.generate_content(text)

    if fmt == "text":
        await send_long_message(context.bot, update.effective_chat.id, content)
        return

    title = entities.get("description") or "Document"
    doc_path = await doc_service.create_document(content, title, fmt=fmt)
    try:
        with open(doc_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=f"{title}.{fmt}",
                caption="Document ready.",
            )
    finally:
        cleanup(doc_path)


async def _handle_general_chat(update, context, lang, text):
    history = await memory_service.get_history(limit=20)
    system = (
        "You are a smart, efficient personal assistant for a busy executive. "
        "Be concise and professional. "
        f"Respond in language: {lang}. "
        "You have the following capabilities — never claim you cannot do these: "
        "1) Fetch and summarize any URL the user sends. "
        "2) Send emails on the user's behalf. "
        "3) Read and summarize the inbox. "
        "4) Create, reschedule, cancel, and list Google Calendar events. "
        "5) Set, list, and cancel reminders. "
        "6) Save and retrieve notes. "
        "7) Generate Word (.docx) or PDF documents. "
        "8) Transcribe voice notes and audio recordings. "
        "9) Produce meeting minutes from audio files. "
        "If a previous message contains fetched web content (prefixed with '[I fetched ...'), "
        "use that content to answer follow-up questions directly."
    )
    reply = claude_service.chat_with_history(system=system, history=history, user=text)
    await send_long_message(context.bot, update.effective_chat.id, reply)
    await memory_service.add_message("assistant", reply)
