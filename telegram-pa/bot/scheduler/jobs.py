import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import ALLOWED_USER_ID, GMAIL_POLL_INTERVAL_MINUTES
from bot.services import reminder_service

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot = None  # set by main.py


def init_scheduler(bot) -> AsyncIOScheduler:
    global _scheduler, _bot
    _bot = bot
    _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def get_scheduler() -> AsyncIOScheduler:
    assert _scheduler is not None, "Scheduler not initialised"
    return _scheduler


async def fire_reminder(reminder_id: int, overdue: bool = False) -> None:
    reminder = await reminder_service.get_by_id(reminder_id)
    if reminder is None or reminder.status != "pending":
        return

    prefix = "⏰ (overdue) " if overdue else "⏰ Reminder: "
    text = f"{prefix}{reminder.description}"
    try:
        await _bot.send_message(chat_id=ALLOWED_USER_ID, text=text)
    except Exception as exc:
        logger.error("Failed to send reminder %s: %s", reminder_id, exc)
    finally:
        await reminder_service.mark_fired(reminder_id)


def schedule_reminder(reminder) -> None:
    remind_at = datetime.fromisoformat(reminder.remind_at.replace("Z", "+00:00"))
    _scheduler.add_job(
        fire_reminder,
        trigger=DateTrigger(run_date=remind_at, timezone="UTC"),
        args=[reminder.id],
        id=reminder.job_id,
        replace_existing=True,
    )


async def restore_pending_reminders() -> None:
    now = datetime.now(timezone.utc)
    reminders = await reminder_service.list_pending()
    for r in reminders:
        remind_at = datetime.fromisoformat(r.remind_at.replace("Z", "+00:00"))
        if remind_at > now:
            schedule_reminder(r)
        else:
            asyncio.create_task(fire_reminder(r.id, overdue=True))
    logger.info("Restored %d pending reminders", len(reminders))


def start_gmail_poll_job(poll_callback) -> None:
    _scheduler.add_job(
        poll_callback,
        trigger=IntervalTrigger(minutes=GMAIL_POLL_INTERVAL_MINUTES),
        id="gmail_poll",
        replace_existing=True,
    )
