import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
ALLOWED_USER_ID: int = int(os.environ["ALLOWED_USER_ID"])
BOSS_TIMEZONE: str = os.getenv("BOSS_TIMEZONE", "Asia/Kuala_Lumpur")
CLAUDE_HAIKU_MODEL: str = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_SONNET_MODEL: str = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-6")
GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "data/credentials.json")
GOOGLE_TOKEN_PATH: str = os.getenv("GOOGLE_TOKEN_PATH", "data/token.json")
DB_PATH: str = os.getenv("DB_PATH", "data/pa.db")

SONNET_INTENTS = {"doc_generate", "meeting_minutes", "email_summarize"}

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
]

GMAIL_POLL_INTERVAL_MINUTES = 15
MAX_TELEGRAM_MESSAGE_LENGTH = 4096
AUDIO_CHUNK_MINUTES = 10
WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24MB safety margin under 25MB limit

CJK_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "assets", "fonts", "NotoSansSC-Regular.ttf"
)
OUTPUT_DIR = "output"
