import asyncio
import base64
import json
import logging
import os
import re
import tempfile

from bot.services import claude_service
from bot.config import CLAUDE_SONNET_MODEL, OUTPUT_DIR

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
You are a business card scanner. Extract all contact details from the image.
Respond ONLY with valid JSON, no prose.

Return this exact schema:
{
  "is_business_card": true|false,
  "full_name": "<string or null>",
  "first_name": "<string or null>",
  "last_name": "<string or null>",
  "title": "<job title or null>",
  "company": "<company name or null>",
  "phones": ["<phone number>", ...],
  "emails": ["<email>", ...],
  "website": "<URL or null>",
  "address": "<full address on one line or null>",
  "notes": "<any other info on card or null>"
}

If image is not a business card, set is_business_card to false and all other fields to null.
"""


def _extract_sync(image_b64: str, media_type: str = "image/jpeg") -> dict:
    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
        },
        {"type": "text", "text": "Extract all contact details from this business card."},
    ]
    import anthropic
    from bot.config import ANTHROPIC_API_KEY
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=CLAUDE_SONNET_MODEL,
        max_tokens=512,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    raw = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {raw!r}")
    return json.loads(match.group())


async def extract_contact(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Returns parsed contact dict if image is a business card, else None."""
    b64 = base64.b64encode(image_bytes).decode()
    try:
        data = await asyncio.to_thread(_extract_sync, b64, media_type)
        if not data.get("is_business_card"):
            return None
        return data
    except Exception as exc:
        logger.error("Contact extraction failed: %s", exc)
        return None


def generate_vcf(contact: dict) -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0"]

    fn = contact.get("full_name") or " ".join(filter(None, [
        contact.get("first_name"), contact.get("last_name")
    ])) or "Unknown"
    lines.append(f"FN:{fn}")

    last = contact.get("last_name", "")
    first = contact.get("first_name", "")
    lines.append(f"N:{last};{first};;;")

    if contact.get("company"):
        lines.append(f"ORG:{contact['company']}")

    if contact.get("title"):
        lines.append(f"TITLE:{contact['title']}")

    for phone in contact.get("phones") or []:
        lines.append(f"TEL;TYPE=WORK,VOICE:{phone}")

    for email in contact.get("emails") or []:
        lines.append(f"EMAIL;TYPE=INTERNET:{email}")

    if contact.get("website"):
        lines.append(f"URL:{contact['website']}")

    if contact.get("address"):
        lines.append(f"ADR;TYPE=WORK:;;{contact['address']};;;;")

    if contact.get("notes"):
        lines.append(f"NOTE:{contact['notes']}")

    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def save_vcf(contact: dict) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fn = contact.get("full_name") or "contact"
    safe = re.sub(r"[^\w\s-]", "", fn).strip().replace(" ", "_")
    path = os.path.join(OUTPUT_DIR, f"{safe}.vcf")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_vcf(contact))
    return path


def format_contact_summary(contact: dict) -> str:
    parts = []
    if contact.get("full_name"):
        parts.append(f"Name: {contact['full_name']}")
    if contact.get("title"):
        parts.append(f"Title: {contact['title']}")
    if contact.get("company"):
        parts.append(f"Company: {contact['company']}")
    for p in contact.get("phones") or []:
        parts.append(f"Phone: {p}")
    for e in contact.get("emails") or []:
        parts.append(f"Email: {e}")
    if contact.get("website"):
        parts.append(f"Website: {contact['website']}")
    if contact.get("address"):
        parts.append(f"Address: {contact['address']}")
    return "\n".join(parts)
