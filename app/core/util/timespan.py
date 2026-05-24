from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# None 을 비교 안전한 sentinel 로 normalize 할 때 사용. UTC tz-aware 라야 Postgres timestamptz / 다른 aware datetime 과 비교 가능.
_AWARE_MIN = datetime.min.replace(tzinfo=timezone.utc)
_AWARE_MAX = datetime.max.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class TimeSpan:
    """[starts_at, ends_at] 시간 구간. None 은 "제약 없음" 으로 처리되어 비교에서 자연스럽게 무한 sentinel 이 된다.

    - `effective_*` 는 비교 / 포함 검사용 (None → AWARE_MIN/MAX).
    - `starts_at` / `ends_at` 은 raw 값. "지정 여부" 가 의미를 갖는 admin 검증에서는 그대로 사용.
    - `x in span` — `x` 가 `TimeSpan` 이면 포함 관계, `datetime` 이면 instant 포함 여부.
    - `starts_before` / `ends_after` 는 자기 raw 값이 None 이면 비교 자체를 건너뛴다 ("지정 안 함" = "위반 아님").
    """

    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @property
    def effective_starts_at(self) -> datetime:
        return self.starts_at if self.starts_at is not None else _AWARE_MIN

    @property
    def effective_ends_at(self) -> datetime:
        return self.ends_at if self.ends_at is not None else _AWARE_MAX

    @property
    def is_inverted(self) -> bool:
        return self.effective_starts_at > self.effective_ends_at

    def __contains__(self, item: "TimeSpan | datetime") -> bool:
        if isinstance(item, TimeSpan):
            return (
                self.effective_starts_at <= item.effective_starts_at
                and item.effective_ends_at <= self.effective_ends_at
            )
        if isinstance(item, datetime):
            return self.effective_starts_at <= item <= self.effective_ends_at
        return NotImplemented

    def starts_before(self, other: "TimeSpan") -> bool:
        if self.starts_at is None:
            return False
        return self.starts_at < other.effective_starts_at

    def ends_after(self, other: "TimeSpan") -> bool:
        if self.ends_at is None:
            return False
        return self.ends_at > other.effective_ends_at
