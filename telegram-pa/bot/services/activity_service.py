from datetime import datetime, timezone

import aiosqlite

from bot.config import DB_PATH


async def log(
    user_id: int,
    intent: str,
    message: str,
    confidence: float = 0.0,
    status: str = "ok",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    preview = message[:200].replace("\n", " ")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO activity_log (timestamp, user_id, intent, confidence, message, status) VALUES (?,?,?,?,?,?)",
            (now, user_id, intent, round(confidence, 3), preview, status),
        )
        await db.commit()


async def get_recent(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, user_id, intent, confidence, message, status FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
