import asyncio
from bot.config import MAX_TELEGRAM_MESSAGE_LENGTH


def split_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts


async def send_long_message(bot, chat_id: int, text: str, **kwargs) -> None:
    parts = split_message(text)
    for i, part in enumerate(parts):
        await bot.send_message(chat_id=chat_id, text=part, **kwargs)
        if i < len(parts) - 1:
            await asyncio.sleep(0.5)
