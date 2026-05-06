import asyncio
import logging
import re
from zoneinfo import ZoneInfo
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import ALLOWED_USER_IDS, BOSS_TIMEZONE
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
    mute_service,
    activity_service,
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

    if user_id not in ALLOWED_USER_IDS:
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

    elif message.photo:
        await _handle_photo(update, context)
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

    # Cancel referencing recently bulk-created events ("cancel these", "cancel all", "remove them")
    _cancel_words = {"cancel", "remove", "delete", "clear"}
    _ref_words = {"these", "all", "them", "those", "everything", "the meetings", "the events"}
    _tl = text.lower()
    if (
        context.user_data.get("last_bulk_event_ids")
        and any(w in _tl for w in _cancel_words)
        and any(w in _tl for w in _ref_words)
    ):
        ids = context.user_data.pop("last_bulk_event_ids")
        await memory_service.add_message("user", text)
        cancelled_count = 0
        for eid in ids:
            try:
                await calendar_service.cancel_event(eid)
                cancelled_count += 1
            except Exception as exc:
                logger.error("Bulk cancel: failed id=%s: %s", eid, exc)
        reply = f"Done. Cancelled {cancelled_count} event(s) from your calendar."
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
        return

    # Pending bulk calendar — user is replying with a date
    if context.user_data.get("pending_bulk_events"):
        pending = context.user_data.pop("pending_bulk_events")
        await memory_service.add_message("user", text)
        fake_entities = {"events": pending, "date_specified": True}
        # Re-classify with date context so intent_router resolves time_iso
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt
        _tz = _ZI(BOSS_TIMEZONE)
        _now_str = _dt.now(_tz).strftime("%Y-%m-%dT%H:%M:%S %Z")
        date_prompt = (
            f"The user provided a list of events earlier and now replied with a date: '{text}'. "
            f"Return calendar_create_bulk JSON with date_specified=true and all time_iso values resolved to that date. "
            f"Current local time: {_now_str} ({BOSS_TIMEZONE}). "
            f"Events: {pending}"
        )
        result2 = intent_router.classify(date_prompt, detect_language(text))
        await _handle_calendar_create_bulk(update, context, result2.entities, detect_language(text))
        return

    # Pending flight search — user replying with one-way/return
    if context.user_data.get("pending_flight"):
        pf = context.user_data.pop("pending_flight")
        await memory_service.add_message("user", text)
        _tl2 = text.lower()
        return_date = ""
        if any(w in _tl2 for w in ("one way", "one-way", "oneway", "no return", "single")):
            pass  # one-way, no return date
        else:
            # try extract date from reply via intent router
            _pf_result = intent_router.classify(
                f"The return date for a flight is: {text}. Extract flight_date as YYYY-MM-DD.",
                detect_language(text),
            )
            return_date = (_pf_result.entities.get("flight_date") or "")[:10]
        await _send_flight_results(
            update, context,
            pf["origin"], pf["destination"], pf["departure_date"],
            return_date, pf["adults"], detect_language(text),
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
    await activity_service.log(
        user_id=user_id,
        intent=intent,
        message=text,
        confidence=confidence,
        status="low_confidence" if confidence < _CONFIDENCE_THRESHOLD else "ok",
    )

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

    elif intent == "calendar_create_bulk":
        await _handle_calendar_create_bulk(update, context, entities, lang)

    elif intent == "calendar_reschedule":
        await _handle_calendar_reschedule(update, context, entities, lang, text)

    elif intent == "calendar_cancel":
        await _handle_calendar_cancel(update, context, entities, lang, text)

    elif intent == "calendar_cancel_bulk":
        await _handle_calendar_cancel_bulk(update, context, entities, lang)

    elif intent == "calendar_list":
        await _handle_calendar_list(update, context, entities, lang)

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

    elif intent == "email_mute":
        await _handle_email_mute(update, context, entities, text)

    elif intent == "email_unmute":
        await _handle_email_unmute(update, context, entities, text)

    elif intent == "daily_overview":
        await _handle_daily_overview(update, context, lang)

    elif intent == "doc_generate":
        await _handle_doc_generate(update, context, entities, lang, text)

    elif intent == "meeting_minutes":
        await message.reply_text(
            "Please send the meeting audio file as a file attachment (paperclip → File)."
        )

    elif intent == "flight_search":
        await _handle_flight_search(update, context, entities, lang)

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
        system=f"You are a natural, human-sounding PA. Confirm this reminder in one short sentence, casually. Respond in language: {lang}.",
        user=f"Reminder set: {description} at {display_time}",
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
    from bot.services import zoom_service

    name = entities.get("calendar_event_name") or entities.get("description", "Meeting")
    time_iso = entities.get("time_iso")
    duration = entities.get("duration_minutes") or 60

    if not time_iso:
        await update.effective_message.reply_text("Please specify the date and time for the event.")
        return

    zoom = None
    if entities.get("zoom_requested"):
        zoom = await zoom_service.create_meeting(name, time_iso, int(duration))
    description = ""
    if zoom:
        description = f"Zoom Meeting\nJoin: {zoom['join_url']}"
        if zoom.get("password"):
            description += f"\nPassword: {zoom['password']}"

    event = await calendar_service.create_event(name, time_iso, int(duration), description=description)
    display_time = _to_kl(time_iso)

    zoom_line = f"\nZoom: {zoom['join_url']}" if zoom else ""
    reply = strip_markdown(claude_service.chat(
        system=f"You are a natural, human-sounding PA. Confirm this calendar event in one short casual sentence. Respond in language: {lang}.",
        user=f"Event '{name}' created at {display_time} for {duration} minutes.{' A Zoom link has been added.' if zoom else ''}",
    )) + zoom_line

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel event", callback_data=f"cancel_event:{event['id']}")
    ]])
    await update.effective_message.reply_text(reply, reply_markup=keyboard)
    await memory_service.add_message("assistant", reply)


async def _handle_calendar_create_bulk(update, context, entities, lang):
    events = entities.get("events") or []
    if not events:
        await update.effective_message.reply_text("Could not parse any events. Please list each event with a time and title.")
        return

    if not entities.get("date_specified"):
        context.user_data["pending_bulk_events"] = events
        reply = "Which date should I add these events to? (e.g. 1 May)"
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
        return

    created = []
    failed = []
    for ev in events:
        name = ev.get("name") or "Meeting"
        time_iso = ev.get("time_iso")
        duration = int(ev.get("duration_minutes") or 60)
        if not time_iso:
            logger.warning("Bulk create: no time_iso for event '%s'", name)
            failed.append(name)
            continue
        try:
            result = await calendar_service.create_event(name, time_iso, duration)
            event_id = result.get("id")
            logger.info("Bulk create: created event '%s' id=%s", name, event_id)
            created.append(f"• {_to_kl(time_iso)} — {name}")
            context.user_data.setdefault("last_bulk_event_ids", []).append(event_id)
        except Exception as exc:
            logger.error("Bulk create: failed '%s': %s", name, exc)
            failed.append(name)

    lines = ["Done! Added to your calendar:"] + created
    if failed:
        lines.append(f"\nCould not add: {', '.join(failed)}")
    reply = "\n".join(lines)
    await update.effective_message.reply_text(reply)
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


async def _handle_calendar_cancel_bulk(update, context, entities, lang):
    names = entities.get("cancel_event_names") or []
    if not names:
        await update.effective_message.reply_text("Could not determine which events to cancel. Please name them.")
        return

    cancelled = []
    not_found = []
    for name in names:
        event = await calendar_service.find_event_by_name(name)
        if not event:
            not_found.append(name)
            continue
        try:
            await calendar_service.cancel_event(event["id"])
            cancelled.append(f"• {event.get('summary', name)}")
        except Exception:
            not_found.append(name)

    lines = []
    if cancelled:
        lines.append("Cancelled from your calendar:")
        lines.extend(cancelled)
    if not_found:
        lines.append(f"\nCould not find: {', '.join(not_found)}")
    reply = "\n".join(lines) if lines else "No events were cancelled."
    await update.effective_message.reply_text(reply)
    await memory_service.add_message("assistant", reply)


async def _handle_calendar_list(update, context, entities, lang):
    from datetime import datetime, date
    from zoneinfo import ZoneInfo

    # Detect scope from time_iso or description
    description = (entities.get("description") or "").lower()
    time_iso = entities.get("time_iso") or ""
    tz = ZoneInfo(BOSS_TIMEZONE)
    today = datetime.now(tz).date()

    if "today" in description or (time_iso and datetime.fromisoformat(time_iso.replace("Z", "+00:00")).astimezone(tz).date() == today):
        days_ahead = 1
        scope_label = "Today"
    elif "tomorrow" in description:
        days_ahead = 2
        scope_label = "Tomorrow"
    elif "month" in description:
        days_ahead = 30
        scope_label = "This month"
    else:
        days_ahead = 7
        scope_label = "This week"

    events = await calendar_service.list_events(days_ahead=days_ahead)

    # Filter to exact scope
    if days_ahead == 1:
        events = [e for e in events if _event_date(e, tz) == today]
    elif days_ahead == 2:
        tomorrow = date(today.year, today.month, today.day + 1) if today.day < 28 else (today.replace(day=1) if today.month < 12 else date(today.year + 1, 1, 1))
        from datetime import timedelta
        tomorrow = today + timedelta(days=1)
        events = [e for e in events if _event_date(e, tz) == tomorrow]

    text = calendar_service.format_event_list(events, scope_label=scope_label)
    await send_long_message(context.bot, update.effective_chat.id, text)


def _event_date(event: dict, tz) -> "date | None":
    from datetime import datetime, date
    start = event.get("start", {})
    dt_str = start.get("dateTime") or start.get("date", "")
    if not dt_str:
        return None
    try:
        if "T" in dt_str:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(tz).date()
        return date.fromisoformat(dt_str)
    except Exception:
        return None


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


async def _handle_email_mute(update, context, entities, original_text):
    import re as _re
    pattern = (
        entities.get("mute_pattern")
        or entities.get("person")
        or entities.get("topic")
        or entities.get("description")
        or ""
    ).strip()
    if not pattern:
        # fallback: extract email address from raw text
        m = _re.search(r"[\w.+\-]+@[\w\-]+\.[\w.]+", original_text)
        if m:
            pattern = m.group()
    if not pattern:
        await update.effective_message.reply_text("What sender or keyword should I mute? e.g. 'mute tender emails'")
        return
    await mute_service.mute(pattern)
    muted = await mute_service.list_muted()
    reply = f"Muted '{pattern}'. Emails matching that won't show up anymore.\nCurrently muted: {', '.join(muted)}"
    await update.effective_message.reply_text(reply)
    await memory_service.add_message("assistant", reply)


async def _handle_email_unmute(update, context, entities, original_text):
    import re as _re
    pattern = (
        entities.get("mute_pattern")
        or entities.get("person")
        or entities.get("topic")
        or entities.get("description")
        or ""
    ).strip()
    if not pattern:
        m = _re.search(r"[\w.+\-]+@[\w\-]+\.[\w.]+", original_text)
        if m:
            pattern = m.group()
    if not pattern:
        muted = await mute_service.list_muted()
        reply = f"Currently muted: {', '.join(muted) if muted else 'nothing'}"
        await update.effective_message.reply_text(reply)
        return
    removed = await mute_service.unmute(pattern)
    reply = f"Unmuted '{pattern}'." if removed else f"'{pattern}' wasn't in the mute list."
    await update.effective_message.reply_text(reply)
    await memory_service.add_message("assistant", reply)


async def _handle_daily_overview(update, context, lang):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    sections = []

    # Today's calendar events
    try:
        tz = ZoneInfo(BOSS_TIMEZONE)
        today = datetime.now(tz).date()
        events = await calendar_service.list_events(days_ahead=1)
        todays = []
        for e in events:
            start = e.get("start", {})
            dt_str = start.get("dateTime") or start.get("date", "")
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(tz)
                if dt.date() == today:
                    todays.append((dt, e.get("summary", "(no title)")))
            except Exception:
                pass
        if todays:
            lines = [f"Your schedule today ({len(todays)} event(s)):"]
            for dt, title in sorted(todays, key=lambda x: x[0]):
                lines.append(f"  {dt.strftime('%H:%M')}  {title}")
            sections.append("\n".join(lines))
        else:
            sections.append("Nothing on the calendar today.")
    except Exception as exc:
        logger.error("Daily overview calendar error: %s", exc)
        sections.append("Couldn't fetch calendar.")

    # Recent emails
    try:
        digest = await gmail_service.get_emails_summary(max_results=5)
        sections.append(f"Inbox (last 5):\n{digest}")
    except Exception as exc:
        logger.error("Daily overview email error: %s", exc)
        sections.append("Couldn't fetch emails.")

    reply = "\n\n".join(sections)
    await send_long_message(context.bot, update.effective_chat.id, reply)
    await memory_service.add_message("assistant", reply)


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

    # Inject recently uploaded document content if available
    doc_ctx = await memory_service.get_recent_document()
    if doc_ctx:
        prompt = f"{doc_ctx}\n\nUser request: {text}"
    else:
        prompt = text

    await update.effective_message.reply_text("On it...")
    content = await doc_service.generate_content(prompt)

    if content.startswith("DATA_REQUIRED:"):
        clarification = content[len("DATA_REQUIRED:"):].strip()
        reply = f"I need the actual data for this. {clarification} Send it as text or attach a file."
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
        return

    if fmt == "text":
        await send_long_message(context.bot, update.effective_chat.id, content)
        await memory_service.add_message("assistant", f"[Generated text document based on: {text[:80]}]")
        return

    title = entities.get("description") or "Document"
    doc_path = await doc_service.create_document(content, title, fmt=fmt)
    try:
        with open(doc_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=f"{title}.{fmt}",
                caption="Here's your document.",
            )
        await memory_service.add_message("assistant", f"[Generated {fmt.upper()} titled '{title}']")
    finally:
        cleanup(doc_path)


async def _handle_flight_search(update, context, entities, lang):
    from bot.services import flight_service

    origin = (entities.get("origin_iata") or entities.get("origin_city") or "").strip()
    destination = (entities.get("destination_iata") or entities.get("destination_city") or "").strip()
    departure_date = (
        entities.get("flight_date")
        or (entities.get("time_iso", "")[:10] if entities.get("time_iso") else "")
    )
    return_date = (entities.get("return_date") or "")[:10]
    trip_type = entities.get("trip_type") or "unknown"
    adults = int(entities.get("adults") or 1)
    logger.info("Flight search entities: origin=%r dest=%r date=%r trip=%r", origin, destination, departure_date, trip_type)

    if not origin or not destination or not departure_date:
        reply = "Please specify origin, destination and date. E.g. 'Flights from KL to Dubai on 15 May'"
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
        return

    if trip_type == "unknown":
        context.user_data["pending_flight"] = {
            "origin": origin, "destination": destination,
            "departure_date": departure_date, "adults": adults,
        }
        reply = "One-way or return? If return, what's the return date?"
        await update.effective_message.reply_text(reply)
        await memory_service.add_message("assistant", reply)
        return

    await _send_flight_results(update, context, origin, destination, departure_date, return_date, adults, lang)


async def _send_flight_results(update, context, origin, destination, departure_date, return_date, adults, lang):
    from bot.services import flight_service

    await update.effective_message.reply_text(f"Searching flights {origin} → {destination}...")
    prices = await flight_service.search_prices(origin, destination, departure_date, return_date, adults)
    msg = flight_service.build_message(origin, destination, departure_date, return_date, adults, prices)
    gf_url = flight_service.google_flights_url(origin, destination, departure_date, return_date, adults)
    ss_url = flight_service.skyscanner_url(origin, destination, departure_date, return_date, adults)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Google Flights", url=gf_url),
        InlineKeyboardButton("Skyscanner", url=ss_url),
    ]])
    await update.effective_message.reply_text(msg, reply_markup=keyboard)
    await memory_service.add_message("assistant", msg)


async def _handle_general_chat(update, context, lang, text):
    from bot.config import CLAUDE_SONNET_MODEL
    history = await memory_service.get_history(limit=50)
    system = (
        "You are a sharp, efficient personal assistant texting your boss — a busy executive. "
        f"Always respond in this language: {lang}. "
        "Keep replies short and conversational — like a smart human PA would text, not a chatbot. "
        "Use full sentences but stay concise. No bullet-point lists unless the user asks for a list. "
        "No filler phrases like 'Great question!', 'Certainly!', 'Of course!', or 'Happy to help!'. "
        "No sign-offs or closings. Just answer and stop. "
        "You have full access to the boss's Gmail, Google Calendar, and documents — never say otherwise. "
        "If the conversation history has a [DOCUMENT: ...] entry, treat it as the open document — answer questions about it directly. "
        "If asked about something you did earlier in the conversation, refer to the history to answer accurately. "
        "Never recap actions the user didn't ask about."
    )
    reply = claude_service.chat_with_history(system=system, history=history, user=text, model=CLAUDE_SONNET_MODEL)
    await send_long_message(context.bot, update.effective_chat.id, reply)
    await memory_service.add_message("assistant", reply)


async def _handle_photo(update, context):
    from bot.services import contact_service
    import base64

    message = update.effective_message
    caption = (message.caption or "").strip()
    await message.reply_text("Reading image...")

    photo = message.photo[-1]
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:
        logger.error("Photo download failed: %s", exc)
        await message.reply_text("Couldn't download the image. Please try again.")
        return

    image_b64 = base64.b64encode(image_bytes).decode()

    # Try business card first
    contact = await contact_service.extract_contact(image_bytes, media_type="image/jpeg")
    if contact:
        summary = contact_service.format_contact_summary(contact)
        vcf_path = contact_service.save_vcf(contact)
        await message.reply_text(f"Business card scanned:\n\n{summary}\n\nSending contact file...")
        try:
            with open(vcf_path, "rb") as f:
                name = contact.get("full_name") or "contact"
                safe = name.replace(" ", "_")
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=f"{safe}.vcf",
                    caption="Tap to add to contacts.",
                )
            await memory_service.add_message("assistant", f"[Business card scanned: {summary}]")
        except Exception as exc:
            logger.error("VCF send failed: %s", exc)
            await message.reply_text(f"Couldn't send contact file: {exc}")
        finally:
            cleanup(vcf_path)
        return

    # Not a business card — summarize the image
    user_prompt = caption if caption else "Summarize or describe the key content of this image."
    system = (
        "You are a concise document summarizer for a busy executive. "
        "Analyze the image and extract key information clearly and briefly. "
        "If it's a resume: name, role, top skills, experience highlights in 3-5 bullet points. "
        "If it's a document or screenshot of text: main topic and key points. "
        "If it's a table or data: what it shows and notable figures. "
        "Be direct. No filler. Max 150 words unless content warrants more."
    )
    try:
        reply = await asyncio.to_thread(
            claude_service.chat_with_vision,
            system,
            user_prompt,
            [image_b64],
            None,
            1024,
            "image/jpeg",
        )
        await send_long_message(context.bot, update.effective_chat.id, reply)
        await memory_service.add_message("user", f"[Image sent{': ' + caption if caption else ''}]")
        await memory_service.add_message("assistant", reply)
    except Exception as exc:
        logger.error("Image summarization failed: %s", exc)
        await message.reply_text("Couldn't read the image. Please try again.")
