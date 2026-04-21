from datetime import datetime, timezone
import aiosqlite
from bot.config import DB_PATH


async def mute(pattern: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO muted_senders (pattern, created_at) VALUES (?, ?)",
            (pattern.lower().strip(), now),
        )
        await db.commit()


async def unmute(pattern: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM muted_senders WHERE pattern = ?", (pattern.lower().strip(),)
        )
        await db.commit()
        return cur.rowcount > 0


async def list_muted() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT pattern FROM muted_senders ORDER BY created_at") as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def is_muted(sender: str, subject: str) -> bool:
    patterns = await list_muted()
    combined = (sender + " " + subject).lower()
    return any(p in combined for p in patterns)
