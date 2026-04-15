from dataclasses import dataclass
from typing import Optional


@dataclass
class Reminder:
    id: Optional[int]
    user_id: int
    description: str
    remind_at: str       # ISO 8601 UTC
    tz_offset: str       # e.g. "+08:00"
    status: str          # pending | fired | cancelled
    job_id: Optional[str]
    created_at: str


@dataclass
class Note:
    id: Optional[int]
    user_id: int
    content: str
    topic: Optional[str]
    language: str
    created_at: str


@dataclass
class EmailCacheRow:
    id: Optional[int]
    message_id: str
    sender: str
    subject: str
    snippet: str
    important: bool
    summary: Optional[str]
    received_at: str
    notified_at: Optional[str]


@dataclass
class PollState:
    key: str
    value: str
