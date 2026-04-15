import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_ID, OUTPUT_DIR
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
logger = logging.getLogger(__name__)

os.makedirs(OUTPUT_DIR, exist_ok=True)


async def _gmail_poll_job(bot) -> None:
    try:
        emails = await gmail_service.poll_new_emails()
        if emails:
            digest = gmail_service.format_email_digest(emails)
            await send_long_message(bot, ALLOWED_USER_ID, digest)
    except Exception as exc:
        logger.error("Gmail poll error: %s", exc)


async def post_init(application: Application) -> None:
    await init_db()
    logger.info("Database initialised")

    scheduler = jobs.init_scheduler(application.bot)

    await jobs.restore_pending_reminders()

    bot = application.bot
    jobs.start_gmail_poll_job(lambda: asyncio.create_task(_gmail_poll_job(bot)))

    scheduler.start()
    logger.info("Scheduler started")


def main() -> None:
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handlers — documents + audio files first, then voice notes + text
    application.add_handler(
        MessageHandler(
            (filters.Document.ALL | filters.AUDIO) & filters.User(ALLOWED_USER_ID),
            handle_document,
        )
    )
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.VOICE) & filters.User(ALLOWED_USER_ID),
            handle_message,
        )
    )
    application.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
