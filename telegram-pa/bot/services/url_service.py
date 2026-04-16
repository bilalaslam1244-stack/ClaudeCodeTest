import asyncio
import re

import httpx

from bot.services import claude_service

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PA-Bot/1.0)"
}
_MAX_CONTENT_CHARS = 8000


async def fetch_and_summarize(url: str, lang: str = "en") -> str:
    try:
        content = await _fetch_text(url)
    except Exception as exc:
        return f"Could not fetch URL: {exc}"

    system = (
        "You are a concise content summarizer for a busy executive. "
        "Summarize the key points of the webpage content in 3-5 bullet points. "
        "Be direct and professional. "
        f"Respond in language: {lang}."
    )
    user = f"URL: {url}\n\nContent:\n{content[:_MAX_CONTENT_CHARS]}"
    return await asyncio.to_thread(
        claude_service.chat_with_intent, "doc_generate", system, user, 1024
    )


async def _fetch_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    # Strip HTML tags
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text
