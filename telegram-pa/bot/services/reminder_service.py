import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from bot.config import DB_PATH, ALLOWED_USER_ID
from bot.db.models import Reminder


async def create(description: str, remind_at_iso: str, tz_offset: str = "+08:00") -> Reminder:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO reminders (user_id, description, remind_at, tz_offset, status, job_id, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (ALLOWED_USER_ID, description, remind_at_iso, tz_offset, job_id, now),
        )
        await db.commit()
        row_id = cursor.lastrowid

    return Reminder(
        id=row_id,
        user_id=ALLOWED_USER_ID,
        description=description,
        remind_at=remind_at_iso,
        tz_offset=tz_offset,
        status="pending",
        job_id=job_id,
        created_at=now,
    )


async def list_pending() -> list[Reminder]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY remind_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_reminder(r) for r in rows]


async def cancel_by_job_id(job_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE job_id = ? AND status = 'pending'",
            (job_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def mark_fired(reminder_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reminders SET status = 'fired' WHERE id = ?", (reminder_id,)
        )
        await db.commit()


async def get_by_id(reminder_id: int) -> Optional[Reminder]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_reminder(row) if row else None


def _row_to_reminder(row: aiosqlite.Row) -> Reminder:
    return Reminder(
        id=row["id"],
        user_id=row["user_id"],
        description=row["description"],
        remind_at=row["remind_at"],
        tz_offset=row["tz_offset"],
        status=row["status"],
        job_id=row["job_id"],
        created_at=row["created_at"],
    )
