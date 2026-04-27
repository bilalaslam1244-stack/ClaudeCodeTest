import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bot.services import claude_service
from bot.config import CLAUDE_HAIKU_MODEL, BOSS_TIMEZONE

VALID_INTENTS = {
    "reminder_set",
    "reminder_list",
    "reminder_cancel",
    "calendar_create",
    "calendar_create_bulk",
    "calendar_reschedule",
    "calendar_cancel",
    "calendar_cancel_bulk",
    "calendar_list",
    "note_save",
    "note_retrieve",
    "email_check",
    "email_summarize",
    "email_send",
    "email_overview",
    "email_mute",
    "email_unmute",
    "daily_overview",
    "doc_generate",
    "meeting_minutes",
    "url_summarize",
    "flight_search",
    "general_chat",
}

SYSTEM_PROMPT = """\
You are an intent classification engine for a personal assistant bot.
Respond ONLY with valid JSON. No prose, no markdown, no explanation.

Classify the user message into exactly one intent from this list:
reminder_set | reminder_list | reminder_cancel |
calendar_create | calendar_create_bulk | calendar_reschedule | calendar_cancel | calendar_cancel_bulk | calendar_list |
note_save | note_retrieve |
email_check | email_summarize | email_send | email_overview |
daily_overview |
doc_generate | meeting_minutes |
flight_search |
general_chat

Intent definitions (use these to disambiguate):
- daily_overview: user wants a combined view of today — schedule AND emails together ("what's on today", "give me an overview of today", "my schedule and emails", "what do I have today", "morning overview", "today's agenda")
- calendar_list: user wants ONLY calendar events, no emails
- calendar_create: user wants to create ONE calendar event
- calendar_create_bulk: user provides MULTIPLE events/appointments at once (a list or schedule with several time slots)
- calendar_cancel: user wants to cancel ONE specific event by name
- calendar_cancel_bulk: user wants to cancel MULTIPLE events at once ("cancel all my events today", "remove all four events")
- flight_search: user wants to find/search flights ("find flights", "cheapest flight to", "flight from X to Y")
- email_check: user wants to READ or FETCH emails, with or without a count ("give me last 3 emails", "show me my emails", "any new emails", "check emails")
- email_summarize: user explicitly wants a SUMMARY or digest of emails ("summarize my emails", "what are the important emails")
- email_overview: user wants a QUICK LIST of subjects/senders only, no AI summary ("what's in my inbox", "inbox overview")
- email_send: user wants to SEND an email
- email_mute: user wants to mute/block/hide emails from a sender or with a keyword ("mute tender emails", "block emails from X", "hide notifications from Y")
- email_unmute: user wants to unmute/unblock a sender ("unmute tender", "stop blocking X")
- IMPORTANT: "give me last N emails" or "show me N emails" → email_check (not email_overview)

Return this exact JSON schema:
{{
  "intent": "<one of the intents above>",
  "confidence": <float 0.0-1.0>,
  "entities": {{
    "time_iso": "<ISO 8601 UTC datetime string, or null>",
    "description": "<task/event/note description, or null>",
    "topic": "<note topic or search keyword, or null>",
    "output_format": "<docx|pdf|text|null>",
    "calendar_event_name": "<event title, or null>",
    "duration_minutes": <integer or null>,
    "count": <integer number of items requested (e.g. "latest 3 emails" → 3), or null>,
    "person": "<person name, or null>",
    "email_to": "<recipient email address or name, or null>",
    "email_subject": "<email subject line, or null>",
    "email_body": "<email body text, or null>",
    "zoom_requested": <true if user explicitly mentions zoom/video call/zoom link, false otherwise>,
    "events": <for calendar_create_bulk only: array of {{"name": "<title>", "time_iso": "<UTC ISO8601 or null if date unknown>", "duration_minutes": <int>}}, else null>,
    "date_specified": <for calendar_create_bulk only: true if user explicitly stated a date, false if no date was given>,
    "cancel_event_names": <for calendar_cancel_bulk only: array of event name strings to cancel, else null>,
    "origin_iata": "<for flight_search: 3-letter IATA code if known (KUL=Kuala Lumpur/KL, DXB=Dubai, SIN=Singapore, MAA=Chennai, BKK=Bangkok, LHR=London, CDG=Paris, JFK=New York, SYD=Sydney, HKG=Hong Kong), else null>",
    "origin_city": "<for flight_search: origin city or airport name as user said it, e.g. 'Kuala Lumpur', 'KL', 'Dubai'>",
    "destination_iata": "<for flight_search: 3-letter IATA code if known, else null>",
    "destination_city": "<for flight_search: destination city or airport name as user said it>",
    "flight_date": "<for flight_search: departure date as YYYY-MM-DD (e.g. '2026-05-15' for '15 May'), null if not specified>",
    "return_date": "<for flight_search: return date as YYYY-MM-DD if round trip, else null>",
    "adults": <for flight_search: number of passengers, default 1>
  }}
}}

Rules:
- Resolve relative times (today, tomorrow, next Monday) using current LOCAL time: {now} (timezone: {tz})
- When user says "2pm" or "3pm" they mean LOCAL time ({tz}), not UTC
- Convert resolved local times to UTC for time_iso output
- Detected input language: {lang}
- All time_iso values must be in UTC ISO 8601 (e.g. 2025-06-01T09:00:00Z)
- If message is a voice transcript tagged [TRANSCRIPT], treat it as direct spoken input
"""


@dataclass
class IntentResult:
    intent: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in response: {text!r}")


def classify(text: str, lang: str = "en") -> IntentResult:
    local_tz = ZoneInfo(BOSS_TIMEZONE)
    now = datetime.now(local_tz).strftime("%Y-%m-%dT%H:%M:%S %Z")
    system = SYSTEM_PROMPT.format(now=now, tz=BOSS_TIMEZONE, lang=lang)

    raw = claude_service.chat(
        system=system,
        user=text,
        model=CLAUDE_HAIKU_MODEL,
        temperature=0.0,
        max_tokens=512,
    )

    try:
        data = _extract_json(raw)
        intent = data.get("intent", "general_chat")
        if intent not in VALID_INTENTS:
            intent = "general_chat"
        return IntentResult(
            intent=intent,
            confidence=float(data.get("confidence", 0.5)),
            entities=data.get("entities", {}),
            raw=raw,
        )
    except (json.JSONDecodeError, ValueError):
        return IntentResult(
            intent="general_chat",
            confidence=0.0,
            entities={},
            raw=raw,
        )
