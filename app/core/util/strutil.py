from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from uuid import UUID

from core.const.datetime import KOREAN_WEEKDAYS, KST
from core.const.regex import UUID_V4_REGEX


def uuid_to_b64(in_str: UUID | str) -> str:
    if isinstance(in_str, str):
        if not UUID_V4_REGEX.match(in_str):
            raise ValueError(f"Invalid UUID string: {in_str}")
        in_str = UUID(in_str)

    return urlsafe_b64encode(in_str.bytes).decode("utf-8").rstrip("=")


def b64_to_uuid(in_str: str) -> UUID:
    return UUID(bytes=urlsafe_b64decode(in_str + "=" * (-len(in_str) % 4)))


def format_korean_date(value: datetime) -> str:
    local = value.astimezone(KST)
    return f"{local.year}년 {local.month}월 {local.day}일({KOREAN_WEEKDAYS[local.weekday()]})"


def format_korean_date_period(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return ""
    if end is None or start.astimezone(KST).date() == end.astimezone(KST).date():
        return format_korean_date(start)
    return f"{format_korean_date(start)} ~ {format_korean_date(end)}"
