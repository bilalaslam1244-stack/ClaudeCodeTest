import logging
from collections import deque
from datetime import datetime, timezone

_buffer: deque = deque(maxlen=300)
_start_time: datetime = datetime.now(timezone.utc)
_error_count: int = 0


class DashboardLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _error_count
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        entry = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "message": msg,
        }
        _buffer.append(entry)
        if record.levelno >= logging.ERROR:
            _error_count += 1


def get_logs() -> list[dict]:
    return list(reversed(_buffer))


def get_start_time() -> datetime:
    return _start_time


def get_error_count() -> int:
    return _error_count


def setup() -> None:
    handler = DashboardLogHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
