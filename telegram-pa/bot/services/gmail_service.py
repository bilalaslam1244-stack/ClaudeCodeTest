import asyncio
import base64
import logging
import mimetypes
import os
from datetime import datetime, timezone
from email import message_from_bytes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


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

    from bot.services import mute_service
    important_emails = []
    for msg_ref in messages:
        try:
            msg = await asyncio.to_thread(_get_message_sync, creds, msg_ref["id"])
            sender = _extract_header(msg, "From")
            subject = _extract_header(msg, "Subject")
            snippet = msg.get("snippet", "")

            if await mute_service.is_muted(sender, subject):
                continue

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
        return "No important emails since last check."
    lines = ["Important emails:\n"]
    for i, e in enumerate(emails, 1):
        lines.append(
            f"{i}. From: {e['sender']}\n"
            f"   Re: {e['subject']}\n"
            f"   {e['summary']}\n"
        )
    return "\n".join(lines)


def _fetch_recent_sync(creds, max_results: int, from_filter: str | None, exclude_patterns: list[str] | None = None) -> list[dict]:
    service = _build_service_sync(creds)
    query = "in:inbox -category:promotions"
    if from_filter:
        query += f" from:{from_filter}"
    for pat in (exclude_patterns or []):
        # only use as -from: if pattern looks like an email domain/address
        import re as _re
        if _re.search(r"@[\w.\-]+", pat):
            query += f" -from:{pat}"
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    emails = []
    for m in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="full"
            ).execute()
            emails.append({
                "id": m["id"],
                "sender": _extract_header(msg, "From"),
                "subject": _extract_header(msg, "Subject"),
                "body": _decode_body(msg),
                "date": msg.get("internalDate", ""),
            })
        except Exception as exc:
            logger.warning("Could not fetch email %s: %s", m["id"], exc)
    return emails


async def get_emails_summary(max_results: int = 10, from_filter: str | None = None) -> str:
    """Fetch latest inbox emails and return AI-summarized digest. Used for on-demand checks."""
    from bot.services import mute_service
    creds = await get_credentials()
    muted_patterns = await mute_service.list_muted()
    emails = await asyncio.to_thread(_fetch_recent_sync, creds, max_results * 2, from_filter, muted_patterns)
    emails = [e for e in emails if not await mute_service.is_muted(e["sender"], e["subject"])]
    emails = emails[:max_results]
    if not emails:
        suffix = f" from '{from_filter}'" if from_filter else ""
        return f"No emails found{suffix}."

    lines = [f"Latest {len(emails)} email(s):\n"]
    for i, e in enumerate(emails, 1):
        summary = await _summarize_email(e["sender"], e["subject"], e["body"])
        lines.append(
            f"{i}. From: {e['sender']}\n"
            f"   Subject: {e['subject']}\n"
            f"   {summary}\n"
        )
    return "\n".join(lines)


def _send_email_sync(creds, to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    service = _build_service_sync(creds)

    if attachment_path:
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        mime_type, _ = mimetypes.guess_type(attachment_path)
        mime_type = mime_type or "application/octet-stream"
        main_type, sub_type = mime_type.split("/", 1)

        with open(attachment_path, "rb") as f:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(f.read())

        import email.encoders
        email.encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(attachment_path)}",
        )
        msg.attach(part)
    else:
        msg = MIMEText(body, "plain")
        msg["To"] = to
        msg["Subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()


async def send_email(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    creds = await get_credentials()
    return await asyncio.to_thread(_send_email_sync, creds, to, subject, body, attachment_path)


def _find_contact_sync(creds, name: str) -> str | None:
    """Search sent + inbox history for an email address matching the given name."""
    import re as _re
    service = _build_service_sync(creds)
    # Search sent mail and inbox for the name
    for query in [f"to:{name}", f"from:{name}"]:
        try:
            result = service.users().messages().list(
                userId="me", q=query, maxResults=5
            ).execute()
            for msg_ref in result.get("messages", []):
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"],
                    format="metadata",
                    fields="payload/headers"
                ).execute()
                for header in msg.get("payload", {}).get("headers", []):
                    if header["name"].lower() in ("to", "from", "cc"):
                        # Extract email from "Name <email@domain.com>" or bare address
                        match = _re.search(r"[\w.+-]+@[\w.-]+\.\w+", header["value"])
                        if match:
                            addr = match.group()
                            # Check name appears in the header value
                            if name.lower() in header["value"].lower():
                                return addr
        except Exception:
            continue
    return None


async def find_contact_email(name: str) -> str | None:
    """Return an email address for the given name, or None if not found."""
    creds = await get_credentials()
    return await asyncio.to_thread(_find_contact_sync, creds, name)


def _get_overview_sync(creds, max_results: int = 10, exclude_patterns: list[str] | None = None) -> list[dict]:
    """Fetch last N emails from inbox for a quick overview."""
    import re as _re
    service = _build_service_sync(creds)
    query = "in:inbox"
    for pat in (exclude_patterns or []):
        if _re.search(r"@[\w.\-]+", pat):
            query += f" -from:{pat}"
    result = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results,
    ).execute()
    messages = result.get("messages", [])
    emails = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            fields="id,snippet,payload/headers,internalDate"
        ).execute()
        emails.append({
            "sender": _extract_header(msg, "From"),
            "subject": _extract_header(msg, "Subject"),
            "snippet": msg.get("snippet", ""),
            "date": msg.get("internalDate", ""),
        })
    return emails


async def get_inbox_overview(max_results: int = 10) -> str:
    """Return a plain-text overview of the last N inbox emails."""
    from bot.services import mute_service
    creds = await get_credentials()
    muted_patterns = await mute_service.list_muted()
    emails = await asyncio.to_thread(_get_overview_sync, creds, max_results * 2, muted_patterns)
    emails = [e for e in emails if not await mute_service.is_muted(e["sender"], e["subject"])]
    emails = emails[:max_results]
    if not emails:
        return "Inbox is empty."
    lines = [f"Last {len(emails)} emails:\n"]
    for i, e in enumerate(emails, 1):
        lines.append(f"{i}. From: {e['sender']}\n   Re: {e['subject']}\n   {e['snippet'][:120]}\n")
    return "\n".join(lines)
