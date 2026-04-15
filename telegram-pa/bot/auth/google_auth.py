import asyncio
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from bot.config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_SCOPES


def _load_credentials() -> Credentials | None:
    if not os.path.exists(GOOGLE_TOKEN_PATH):
        return None
    creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, GOOGLE_SCOPES)
    return creds


def _refresh_if_needed(creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return creds


def _save_credentials(creds: Credentials) -> None:
    with open(GOOGLE_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    try:
        os.chmod(GOOGLE_TOKEN_PATH, 0o600)
    except OSError:
        pass


def _get_credentials_sync() -> Credentials:
    creds = _load_credentials()
    if creds is None:
        raise RuntimeError(
            "Google credentials not found. Run scripts/google_auth_init.py first."
        )
    return _refresh_if_needed(creds)


async def get_credentials() -> Credentials:
    return await asyncio.to_thread(_get_credentials_sync)
