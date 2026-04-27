import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.services import reminder_service, calendar_service
from bot.scheduler import jobs

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""

    if data.startswith("cancel_reminder:"):
        job_id = data.split(":", 1)[1]
        cancelled = await reminder_service.cancel_by_job_id(job_id)
        try:
            jobs.get_scheduler().remove_job(job_id)
        except Exception:
            pass
        text = "Reminder cancelled." if cancelled else "Reminder not found or already fired."
        await query.edit_message_text(text)

    elif data.startswith("cancel_event:"):
        event_id = data.split(":", 1)[1]
        try:
            await calendar_service.cancel_event(event_id)
            await query.edit_message_text("Calendar event cancelled.")
        except Exception as exc:
            logger.error("Failed to cancel event %s: %s", event_id, exc)
            await query.edit_message_text("Could not cancel the event. Please try again.")

    elif data == "noop":
        await query.edit_message_text("No changes made.")

    else:
        await query.edit_message_text("Unknown action.")
