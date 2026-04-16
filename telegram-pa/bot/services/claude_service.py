import anthropic
from bot.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_HAIKU_MODEL,
    CLAUDE_SONNET_MODEL,
    SONNET_INTENTS,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def select_model(intent: str) -> str:
    return CLAUDE_SONNET_MODEL if intent in SONNET_INTENTS else CLAUDE_HAIKU_MODEL


def chat(
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    response = _client.messages.create(
        model=model or CLAUDE_HAIKU_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def chat_with_intent(intent: str, system: str, user: str, max_tokens: int = 4096) -> str:
    model = select_model(intent)
    return chat(system=system, user=user, model=model, max_tokens=max_tokens)


def chat_with_history(
    system: str,
    history: list[dict],
    user: str,
    model: str | None = None,
    max_tokens: int = 2048,
) -> str:
    messages = list(history) + [{"role": "user", "content": user}]
    response = _client.messages.create(
        model=model or CLAUDE_HAIKU_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text
