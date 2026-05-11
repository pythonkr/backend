from datetime import datetime, timezone
from typing import Any


def now_aware() -> datetime:
    """현재 시각을 로컬 타임존이 반영된 timezone-aware datetime 으로 반환."""
    return datetime.now().astimezone()


def any_to_datetime(value: Any, tzinfo: timezone | None = None, raise_exception: bool = True) -> datetime | None:
    """Convert a string or datetime to a datetime object."""
    if not value:
        return None

    try:
        return (datetime.fromisoformat(value) if isinstance(value, str) else value).replace(tzinfo=tzinfo)
    except Exception as e:
        if raise_exception:
            raise e
        return None
