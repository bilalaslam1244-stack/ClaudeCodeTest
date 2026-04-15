import asyncio
import base64
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from typing import Optional

import aiosqlite
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.auth.google_auth import get_credentials
from bot.config import DB_PATH, CLAUDE_HAIKU_MODEL
from bot.services import claude_service

logger = logging.getLogger(__name__)

_IMPORTANCE_SYSTEM = """\
You are an email importance classifier for a busy executive.
Respond ONLY with JSON: {"important": true|false, "summary": "<one sentence>"}
Mark important if: from a known business contact or VIP, requires action/response,
mentions deadlines, contracts, payments, meetings, or urgent matters.
Mark NOT important if: newsletters, promotions, automated notifications, social media.
"""


def _build_service_sync(creds):
    return build("gmail", "v1", credentials=creds)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_messages_sync(creds, since_timestamp: int, max_results: int = 30) -> list[dict]:
    service = _build_service_sync(creds)
    query = f"after:{since_timestamp} in:inbox -category:promotions -category:social"
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return result.get("messages", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get_message_sync(creds, msg_id: str, full: bool = False) -> dict:
    service = _build_service_sync(creds)
    fmt = "full" if full else "metadata"
    fields = None if full else "id,snippet,payload/headers,internalDate"
    return service.users().messages().get(
        userId="me", id=msg_id, format=fmt, fields=fields
    ).execute()


def _extract_header(msg: dict, name: str) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(msg: dict) -> str:
    """Extract plain-text body from a Gmail message."""
    payload = msg.get("payload", {})

    def _get_parts(p):
        if p.get("mimeType") == "text/plain":
            data = p.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for part in p.get("parts", []):
            result = _get_parts(part)
            if result:
                return result
        return ""

    return _get_parts(payload) or msg.get("snippet", "")


def _score_importance_sync(sender: str, subject: str, snippet: str) -> dict:
    import json, re
    prompt = f"From: {sender}\nSubject: {subject}\nPreview: {snippet}"
    raw = claude_service.chat(
        system=_IMPORTANCE_SYSTEM,
        user=prompt,
        model=CLAUDE_HAIKU_MODEL,
        temperature=0.0,
        max_tokens=128,
    )
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group()) if match else {"important": False, "summary": snippet[:100]}
    except Exception:
        return {"important": False, "summary": snippet[:100]}


async def _get_last_poll_timestamp() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM poll_state WHERE key = 'gmail_last_poll'"
        ) as cur:
            row = await cur.fetchone()
    if row:
        return int(row[0])
    return int(datetime.now(timezone.utc).timestamp()) - 86400  # default: last 24h


async def _save_poll_timestamp(ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO poll_state (key, value) VALUES ('gmail_last_poll', ?)",
            (str(ts),),
        )
        await db.commit()


async def poll_new_emails() -> list[dict]:
    """Fetch new emails, score importance, return important ones with summaries."""
    creds = await get_credentials()
    since_ts = await _get_last_poll_timestamp()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    messages = await asyncio.to_thread(_fetch_messages_sync, creds, since_ts)
    if not messages:
        await _save_poll_timestamp(now_ts)
        return []

    important_emails = []
    for msg_ref in messages:
        try:
            msg = await asyncio.to_thread(_get_message_sync, creds, msg_ref["id"])
            sender = _extract_header(msg, "From")
            subject = _extract_header(msg, "Subject")
            snippet = msg.get("snippet", "")

            score = await asyncio.to_thread(_score_importance_sync, sender, subject, snippet)
            if score.get("important"):
                full_msg = await asyncio.to_thread(_get_message_sync, creds, msg_ref["id"], full=True)
                body = _decode_body(full_msg)
                summary = await _summarize_email(sender, subject, body)
                important_emails.append({
                    "id": msg_ref["id"],
                    "sender": sender,
                    "subject": subject,
                    "summary": summary,
                })
        except Exception as exc:
            logger.warning("Error processing email %s: %s", msg_ref["id"], exc)

    await _save_poll_timestamp(now_ts)
    return important_emails


async def _summarize_email(sender: str, subject: str, body: str) -> str:
    system = (
        "You are a concise email summarizer for an executive. "
        "Summarize the key points and any required actions in 2-4 sentences. "
        "Be direct and professional."
    )
    user = f"From: {sender}\nSubject: {subject}\n\n{body[:3000]}"
    return await asyncio.to_thread(
        claude_service.chat_with_intent, "email_summarize", system, user, 512
    )


def format_email_digest(emails: list[dict]) -> str:
    if not emails:
        return "No important emails."
    lines = ["*Important emails:*\n"]
    for i, e in enumerate(emails, 1):
        lines.append(
            f"{i}. *From:* {e['sender']}\n"
            f"   *Re:* {e['subject']}\n"
            f"   {e['summary']}\n"
        )
    return "\n".join(lines)
