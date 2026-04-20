import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.auth.google_auth import get_credentials
from bot.config import BOSS_TIMEZONE


def _build_service_sync(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _create_event_sync(creds, summary: str, start_iso: str, duration_minutes: int, description: str = "") -> dict:
    service = _build_service_sync(creds)
    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": BOSS_TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": BOSS_TIMEZONE},
    }
    return service.events().insert(calendarId="primary", body=event).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _list_events_sync(creds, days_ahead: int = 7) -> list[dict]:
    service = _build_service_sync(creds)
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _find_event_by_name_sync(creds, name: str) -> Optional[dict]:
    service = _build_service_sync(creds)
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=30)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        q=name,
        maxResults=5,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    items = result.get("items", [])
    return items[0] if items else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _update_event_sync(creds, event_id: str, new_start_iso: str, duration_minutes: int) -> dict:
    service = _build_service_sync(creds)
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    start_dt = datetime.fromisoformat(new_start_iso.replace("Z", "+00:00"))
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": BOSS_TIMEZONE}
    event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": BOSS_TIMEZONE}
    return service.events().update(calendarId="primary", eventId=event_id, body=event).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _delete_event_sync(creds, event_id: str) -> None:
    service = _build_service_sync(creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()


async def create_event(summary: str, start_iso: str, duration_minutes: int = 60, description: str = "") -> dict:
    creds = await get_credentials()
    return await asyncio.to_thread(_create_event_sync, creds, summary, start_iso, duration_minutes, description)


async def list_events(days_ahead: int = 7) -> list[dict]:
    creds = await get_credentials()
    return await asyncio.to_thread(_list_events_sync, creds, days_ahead)


async def find_event_by_name(name: str) -> Optional[dict]:
    creds = await get_credentials()
    return await asyncio.to_thread(_find_event_by_name_sync, creds, name)


async def reschedule_event(event_id: str, new_start_iso: str, duration_minutes: int = 60) -> dict:
    creds = await get_credentials()
    return await asyncio.to_thread(_update_event_sync, creds, event_id, new_start_iso, duration_minutes)


async def cancel_event(event_id: str) -> None:
    creds = await get_credentials()
    await asyncio.to_thread(_delete_event_sync, creds, event_id)


def format_event_list(events: list[dict], tz: str = BOSS_TIMEZONE) -> str:
    if not events:
        return "No upcoming events."
    lines = []
    for e in events:
        start = e.get("start", {})
        dt_str = start.get("dateTime") or start.get("date", "")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                dt_str = dt.strftime("%a %d %b %Y, %H:%M")
            except ValueError:
                pass
        lines.append(f"• {e.get('summary', '(no title)')} — {dt_str}")
    return "\n".join(lines)
