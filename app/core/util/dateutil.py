from datetime import datetime, timezone
from typing import Any


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
