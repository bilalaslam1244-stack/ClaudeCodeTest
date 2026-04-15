import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.services import claude_service
from bot.config import CLAUDE_HAIKU_MODEL

VALID_INTENTS = {
    "reminder_set",
    "reminder_list",
    "reminder_cancel",
    "calendar_create",
    "calendar_reschedule",
    "calendar_cancel",
    "calendar_list",
    "note_save",
    "note_retrieve",
    "email_check",
    "email_summarize",
    "email_send",
    "email_overview",
    "doc_generate",
    "meeting_minutes",
    "general_chat",
}

SYSTEM_PROMPT = """\
You are an intent classification engine for a personal assistant bot.
Respond ONLY with valid JSON. No prose, no markdown, no explanation.

Classify the user message into exactly one intent from this list:
reminder_set | reminder_list | reminder_cancel |
calendar_create | calendar_reschedule | calendar_cancel | calendar_list |
note_save | note_retrieve |
email_check | email_summarize | email_send | email_overview |
doc_generate | meeting_minutes |
general_chat

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
    "person": "<person name, or null>",
    "email_to": "<recipient email address or name, or null>",
    "email_subject": "<email subject line, or null>",
    "email_body": "<email body text, or null>"
  }}
}}

Rules:
- Resolve relative times (today, tomorrow, next Monday) using current UTC time: {now}
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
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    system = SYSTEM_PROMPT.format(now=now, lang=lang)

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
