from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from bot.config import DB_PATH, ALLOWED_USER_ID
from bot.db.models import Note


async def save(content: str, topic: Optional[str] = None, language: str = "en") -> Note:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "INSERT INTO notes (user_id, content, topic, language, created_at) VALUES (?, ?, ?, ?, ?)",
            (ALLOWED_USER_ID, content, topic, language, now),
        )
        await db.commit()
        row_id = cursor.lastrowid
    return Note(id=row_id, user_id=ALLOWED_USER_ID, content=content,
                topic=topic, language=language, created_at=now)


async def search(keyword: Optional[str] = None, limit: int = 10) -> list[Note]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if keyword:
            async with db.execute(
                "SELECT * FROM notes WHERE content LIKE ? OR topic LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{keyword}%", f"%{keyword}%", limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
    return [_row_to_note(r) for r in rows]


def format_notes(notes: list[Note]) -> str:
    if not notes:
        return "No notes found."
    lines = []
    for n in notes:
        date = n.created_at[:10]
        topic = f"[{n.topic}] " if n.topic else ""
        lines.append(f"• {date} {topic}{n.content[:200]}")
    return "\n".join(lines)


def _row_to_note(row: aiosqlite.Row) -> Note:
    return Note(
        id=row["id"],
        user_id=row["user_id"],
        content=row["content"],
        topic=row["topic"],
        language=row["language"],
        created_at=row["created_at"],
    )
