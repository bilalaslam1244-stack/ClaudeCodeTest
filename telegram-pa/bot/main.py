import logging
import os
import threading

import uvicorn
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_ID, ALLOWED_USER_IDS, OUTPUT_DIR, TELEGRAM_LOCAL_API_URL
from bot.dashboard import log_buffer as _log_buffer
from bot.db.database import init_db
from bot.handlers.message_handler import handle_message
from bot.handlers.document_handler import handle_document
from bot.handlers.callback_handler import handle_callback
from bot.scheduler import jobs
from bot.services import gmail_service
from bot.utils.formatting import send_long_message

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
_log_buffer.setup()
logger = logging.getLogger(__name__)

os.makedirs(OUTPUT_DIR, exist_ok=True)


def _start_dashboard() -> None:
    import asyncio
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
        from bot.dashboard.app import app, DASHBOARD_PORT
        logger.info("Dashboard starting on port %s", DASHBOARD_PORT)
        uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="warning")
    except Exception as exc:
        logger.error("Dashboard failed to start: %s", exc, exc_info=True)


threading.Thread(target=_start_dashboard, daemon=True).start()


async def _gmail_poll_job(bot) -> None:
    try:
        emails = await gmail_service.poll_new_emails()
        if emails:
            digest = gmail_service.format_email_digest(emails)
            await send_long_message(bot, ALLOWED_USER_ID, digest)
    except Exception as exc:
        logger.error("Gmail poll error: %s", exc)


async def _daily_overview_job(bot) -> None:
    from bot.services import calendar_service
    from zoneinfo import ZoneInfo
    from datetime import datetime
    from bot.config import BOSS_TIMEZONE

    sections = ["Good morning! Here's your daily overview:\n"]

    # Today's calendar events
    try:
        events = await calendar_service.list_events(days_ahead=1)
        tz = ZoneInfo(BOSS_TIMEZONE)
        today = datetime.now(tz).date()
        todays_events = []
        for e in events:
            start = e.get("start", {})
            dt_str = start.get("dateTime") or start.get("date", "")
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(tz)
                if dt.date() == today:
                    todays_events.append((dt, e))
            except Exception:
                pass
        if todays_events:
            lines = ["Calendar today:"]
            for dt, e in sorted(todays_events, key=lambda x: x[0]):
                lines.append(f"  • {dt.strftime('%H:%M')} — {e.get('summary', '(no title)')}")
            sections.append("\n".join(lines))
        else:
            sections.append("Calendar today: No events scheduled.")
    except Exception as exc:
        logger.error("Daily overview calendar error: %s", exc)
        sections.append("Calendar today: Could not fetch events.")

    # Inbox highlights
    try:
        overview = await gmail_service.get_inbox_overview(max_results=5)
        sections.append(f"Inbox highlights:\n{overview}")
    except Exception as exc:
        logger.error("Daily overview inbox error: %s", exc)
        sections.append("Inbox: Could not fetch emails.")

    try:
        await send_long_message(bot, ALLOWED_USER_ID, "\n\n".join(sections))
    except Exception as exc:
        logger.error("Daily overview send error: %s", exc)


async def post_init(application: Application) -> None:
    await init_db()
    logger.info("Database initialised")

    bot = application.bot
    scheduler = jobs.init_scheduler(bot)

    await jobs.restore_pending_reminders()

    async def _poll_wrapper():
        await _gmail_poll_job(bot)

    async def _overview_wrapper():
        await _daily_overview_job(bot)

    jobs.start_gmail_poll_job(_poll_wrapper)
    jobs.start_daily_overview_job(_overview_wrapper)

    scheduler.start()
    logger.info("Scheduler started")


def main() -> None:
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init)
    if TELEGRAM_LOCAL_API_URL:
        builder = builder.base_url(TELEGRAM_LOCAL_API_URL)
        logger.info("Using local Telegram Bot API: %s", TELEGRAM_LOCAL_API_URL)
    application = builder.build()

    # Handlers — documents + audio files first, then voice notes + text
    application.add_handler(
        MessageHandler(
            (filters.Document.ALL | filters.AUDIO) & filters.User(ALLOWED_USER_IDS),
            handle_document,
        )
    )
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.VOICE | filters.PHOTO) & filters.User(ALLOWED_USER_IDS),
            handle_message,
        )
    )
    application.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
