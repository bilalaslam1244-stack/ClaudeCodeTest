import asyncio
import base64
import logging
import time
from datetime import datetime, timezone

import httpx

from bot.config import ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, BOSS_TIMEZONE

logger = logging.getLogger(__name__)

_token_cache: dict = {"token": None, "expires_at": 0}

ZOOM_ENABLED = bool(ZOOM_ACCOUNT_ID and ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET)


def _get_token_sync() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    credentials = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    with httpx.Client() as client:
        resp = client.post(
            "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID},
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)
    return _token_cache["token"]


def _create_meeting_sync(topic: str, start_iso: str, duration_minutes: int) -> dict:
    token = _get_token_sync()
    # Zoom expects UTC in format: 2025-06-01T09:00:00Z
    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    start_zoom = start_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "topic": topic,
        "type": 2,  # scheduled meeting
        "start_time": start_zoom,
        "duration": duration_minutes,
        "timezone": BOSS_TIMEZONE,
        "settings": {
            "host_video": True,
            "participant_video": True,
            "join_before_host": True,
            "waiting_room": False,
            "mute_upon_entry": False,
        },
    }
    with httpx.Client() as client:
        resp = client.post(
            "https://api.zoom.us/v2/users/me/meetings",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def create_meeting(topic: str, start_iso: str, duration_minutes: int = 60) -> dict | None:
    """Create a Zoom meeting. Returns dict with join_url and password, or None on failure."""
    if not ZOOM_ENABLED:
        return None
    try:
        data = await asyncio.to_thread(_create_meeting_sync, topic, start_iso, duration_minutes)
        return {
            "join_url": data.get("join_url", ""),
            "password": data.get("password", ""),
            "meeting_id": data.get("id", ""),
        }
    except Exception as exc:
        logger.warning("Zoom meeting creation failed: %s", exc)
        return None
