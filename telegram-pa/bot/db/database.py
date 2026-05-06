import aiosqlite
from bot.config import DB_PATH


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                description TEXT    NOT NULL,
                remind_at   TEXT    NOT NULL,
                tz_offset   TEXT    NOT NULL DEFAULT '+08:00',
                status      TEXT    NOT NULL DEFAULT 'pending',
                job_id      TEXT,
                created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                content     TEXT    NOT NULL,
                topic       TEXT,
                language    TEXT    NOT NULL DEFAULT 'en',
                created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  TEXT    NOT NULL UNIQUE,
                sender      TEXT    NOT NULL,
                subject     TEXT    NOT NULL,
                snippet     TEXT,
                important   INTEGER NOT NULL DEFAULT 0,
                summary     TEXT,
                received_at TEXT    NOT NULL,
                notified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS poll_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS muted_senders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern    TEXT    NOT NULL UNIQUE,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                user_id     INTEGER NOT NULL,
                intent      TEXT    NOT NULL,
                confidence  REAL    NOT NULL DEFAULT 0,
                message     TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'ok'
            );
        """)
        await db.commit()
