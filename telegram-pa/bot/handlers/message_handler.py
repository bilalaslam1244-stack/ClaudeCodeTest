import logging

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
)
from bot.scheduler import jobs
from bot.utils.language import detect_language
from bot.utils.formatting import send_long_message
from bot.utils.file_utils import cleanup

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.65


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else None

    # Allowlist gate
    if user_id != ALLOWED_USER_ID:
        return

    # Resolve text: transcribe voice, or use text directly
    text = ""
    is_voice = False

    if message.voice or (message.audio and not message.document):
        try:
            await message.reply_text("Transcribing...")
            text = await voice_handler.download_and_transcribe(update, context)
            is_voice = True
            from bot.utils.formatting import split_message
            for part in split_message(f"[Transcript]\n{text}"):
                await message.reply_text(part)
        except Exception as exc:
            logger.error("Voice transcription failed: %s", exc)
            await message.reply_text("Could not transcribe the audio. Please try again.")
            return
    elif message.text:
        text = message.text.strip()
    else:
        return  # documents handled by document_handler

    if not text:
        return

    # Language detection
    lang = detect_language(text)
    if is_voice:
        tagged = f"[TRANSCRIPT] {text}"
    else:
        tagged = text

    # Intent classification
    result = intent_router.classify(tagged, lang)
    intent = result.intent
    entities = result.entities
    confidence = result.confidence

    logger.info("Intent: %s (%.2f) | lang: %s", intent, confidence, lang)

    # Low confidence — ask for clarification via Claude
    if confidence < _CONFIDENCE_THRESHOLD:
        clarify = claude_service.chat(
            system=f"You are a helpful PA. The user said something ambiguous. "
                   f"Ask a short clarifying question in language: {lang}.",
            user=text,
        )
        await message.reply_text(clarify)
        return

    # ── Dispatch ──────────────────────────────────────────────────────────────

    if intent == "reminder_set":
        await _handle_reminder_set(update, context, entities, lang, text)

    elif intent == "reminder_list":
        await _handle_reminder_list(update, context, lang)

    elif intent == "reminder_cancel":
        await _handle_reminder_cancel(update, context, entities, lang, text)

    elif intent in ("calendar_create",):
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
        await _handle_email_check(update, context, lang)

    elif intent == "doc_generate":
        await _handle_doc_generate(update, context, entities, lang, text)

    elif intent == "meeting_minutes":
        await message.reply_text(
            "Please send the meeting audio file directly as a file attachment."
        )

    else:  # general_chat
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

    reply = claude_service.chat(
        system=f"Confirm a reminder was set. Be brief. Respond in language: {lang}.",
        user=f"Reminder: {description} at {time_iso} (timezone: {BOSS_TIMEZONE})",
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel reminder", callback_data=f"cancel_reminder:{reminder.job_id}")
    ]])
    await update.effective_message.reply_text(reply, reply_markup=keyboard)


async def _handle_reminder_list(update, context, lang):
    reminders = await reminder_service.list_pending()
    if not reminders:
        await update.effective_message.reply_text("No pending reminders.")
        return

    lines = []
    keyboard_rows = []
    for r in reminders:
        lines.append(f"• {r.remind_at[:16]} — {r.description}")
        keyboard_rows.append([
            InlineKeyboardButton(
                f"Cancel: {r.description[:20]}",
                callback_data=f"cancel_reminder:{r.job_id}"
            )
        ])
    text = "Pending reminders:\n" + "\n".join(lines)
    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows))


async def _handle_reminder_cancel(update, context, entities, lang, original_text):
    description = entities.get("description") or original_text
    reminders = await reminder_service.list_pending()
    if not reminders:
        await update.effective_message.reply_text("No pending reminders to cancel.")
        return

    # Fuzzy match via Claude
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
    if cancelled:
        await update.effective_message.reply_text("Reminder cancelled.")
    else:
        await update.effective_message.reply_text("Could not find that reminder.")


async def _handle_calendar_create(update, context, entities, lang):
    name = entities.get("calendar_event_name") or entities.get("description", "Meeting")
    time_iso = entities.get("time_iso")
    duration = entities.get("duration_minutes") or 60

    if not time_iso:
        await update.effective_message.reply_text("Please specify the date and time for the event.")
        return

    event = await calendar_service.create_event(name, time_iso, int(duration))
    reply = claude_service.chat(
        system=f"Confirm a calendar event was created. Be brief. Respond in language: {lang}.",
        user=f"Event '{name}' created at {time_iso} for {duration} minutes.",
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel event", callback_data=f"cancel_event:{event['id']}")
    ]])
    await update.effective_message.reply_text(reply, reply_markup=keyboard)


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
    await update.effective_message.reply_text(
        f"Rescheduled '{event.get('summary')}' to {new_time[:16]}."
    )


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
    note = await notes_service.save(text, topic=topic, language=lang)
    await update.effective_message.reply_text(
        f"Note saved." + (f" Topic: {topic}" if topic else "")
    )


async def _handle_note_retrieve(update, context, entities, lang):
    keyword = entities.get("topic") or entities.get("description")
    notes = await notes_service.search(keyword=keyword)
    text = notes_service.format_notes(notes)
    await send_long_message(context.bot, update.effective_chat.id, text)


async def _handle_email_check(update, context, lang):
    await update.effective_message.reply_text("Checking emails...")
    emails = await gmail_service.poll_new_emails()
    digest = gmail_service.format_email_digest(emails)
    await send_long_message(context.bot, update.effective_chat.id, digest)


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
    system = (
        "You are a smart, efficient personal assistant for a busy executive. "
        "Be concise and professional. "
        f"Respond in language: {lang}."
    )
    reply = claude_service.chat(system=system, user=text)
    await send_long_message(context.bot, update.effective_chat.id, reply)
