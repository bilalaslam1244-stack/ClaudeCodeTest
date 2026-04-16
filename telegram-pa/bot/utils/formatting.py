import asyncio
import re

from bot.config import MAX_TELEGRAM_MESSAGE_LENGTH


def strip_markdown(text: str) -> str:
    """Remove markdown formatting symbols so plain-text Telegram messages are clean."""
    # Bold/italic markers
    text = re.sub(r'\*{1,3}', '', text)
    text = re.sub(r'_{1,2}', '', text)
    # Headings (## Heading → Heading)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Inline code
    text = re.sub(r'`+', '', text)
    return text


def split_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts


async def send_long_message(bot, chat_id: int, text: str, **kwargs) -> None:
    text = strip_markdown(text)
    parts = split_message(text)
    for i, part in enumerate(parts):
        await bot.send_message(chat_id=chat_id, text=part, **kwargs)
        if i < len(parts) - 1:
            await asyncio.sleep(0.5)
