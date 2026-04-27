"""
Sliding-window conversation memory stored in SQLite.
Keeps the last WINDOW_SIZE exchanges and injects them into Claude context.
"""
from datetime import datetime, timezone

import aiosqlite

from bot.config import DB_PATH, ALLOWED_USER_ID

WINDOW_SIZE = 40  # last 40 messages (20 exchanges)


async def add_message(role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversation_history (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (ALLOWED_USER_ID, role, content, now),
        )
        await db.commit()

        # Prune: keep only the most recent WINDOW_SIZE * 3 rows to avoid unbounded growth
        await db.execute(
            """DELETE FROM conversation_history WHERE id NOT IN (
                SELECT id FROM conversation_history
                WHERE user_id = ?
                ORDER BY id DESC LIMIT ?
            )""",
            (ALLOWED_USER_ID, WINDOW_SIZE * 4),
        )
        await db.commit()


async def get_history(limit: int = WINDOW_SIZE) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT role, content FROM conversation_history
               WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (ALLOWED_USER_ID, limit),
        ) as cur:
            rows = await cur.fetchall()
    # Reverse so oldest first (correct order for Claude)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def get_recent_document(limit: int = 30) -> str | None:
    """Return content of the most recently uploaded document from history, or None."""
    history = await get_history(limit=limit)
    for msg in reversed(history):
        if msg["role"] == "user" and msg["content"].startswith("[DOCUMENT:"):
            return msg["content"]
    return None


async def clear_history() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM conversation_history WHERE user_id = ?", (ALLOWED_USER_ID,)
        )
        await db.commit()
