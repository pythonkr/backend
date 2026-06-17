from datetime import datetime, timedelta, timezone
from typing import Any

from core.const.datetime import KST, Granularity


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


def period_start(dt: datetime, granularity: Granularity) -> datetime:
    """`dt` 를 granularity 주기 시작(KST)으로 정렬."""
    d = dt.astimezone(KST)
    if granularity == Granularity.HOUR:
        return d.replace(minute=0, second=0, microsecond=0)
    if granularity == Granularity.DAY:
        return d.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == Granularity.WEEK:
        d0 = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return d0 - timedelta(days=d0.weekday())  # 월요일 시작 (TruncWeek 동일)
    if granularity == Granularity.MONTH:
        return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown granularity: {granularity}")


def period_label(dt: datetime, granularity: Granularity) -> str:
    """`dt` 가 속한 granularity 주기의 라벨 문자열."""
    d = period_start(dt, granularity)
    if granularity == Granularity.HOUR:
        return d.strftime("%Y-%m-%d %H:%M")
    if granularity == Granularity.MONTH:
        return d.strftime("%Y-%m")
    return d.strftime("%Y-%m-%d")


def _next_period(dt: datetime, granularity: Granularity) -> datetime:
    if granularity == Granularity.HOUR:
        return dt + timedelta(hours=1)
    if granularity == Granularity.DAY:
        return dt + timedelta(days=1)
    if granularity == Granularity.WEEK:
        return dt + timedelta(weeks=1)
    if granularity == Granularity.MONTH:
        year, month = dt.year + dt.month // 12, dt.month % 12 + 1
        return dt.replace(year=year, month=month)
    raise ValueError(f"unknown granularity: {granularity}")


def period_label_range(date_from: datetime, date_to: datetime, granularity: Granularity) -> list[str]:
    """`[date_from, date_to)` 를 granularity 로 끊은 연속 주기 라벨(정렬)."""
    labels: list[str] = []
    cur = period_start(date_from, granularity)
    while cur < date_to:
        labels.append(period_label(cur, granularity))
        cur = _next_period(cur, granularity)
    return labels
