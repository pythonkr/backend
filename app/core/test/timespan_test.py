from datetime import datetime, timezone

from core.util.timespan import TimeSpan

_T = lambda y: datetime(y, 1, 1, tzinfo=timezone.utc)  # noqa: E731


def test_is_inverted_false_when_starts_at_equal_or_before_ends_at():
    assert TimeSpan(_T(2020), _T(2030)).is_inverted is False
    assert TimeSpan(_T(2020), _T(2020)).is_inverted is False


def test_is_inverted_true_when_starts_at_after_ends_at():
    assert TimeSpan(_T(2030), _T(2020)).is_inverted is True


def test_is_inverted_false_when_either_endpoint_none():
    # None 은 무한 sentinel — start=None → AWARE_MIN, end=None → AWARE_MAX. 둘 다 비교 시 항상 정상 순서.
    assert TimeSpan(None, _T(2020)).is_inverted is False
    assert TimeSpan(_T(2020), None).is_inverted is False
    assert TimeSpan(None, None).is_inverted is False


def test_contains_timespan_true_when_outer_envelopes_inner():
    outer = TimeSpan(_T(2020), _T(2030))
    inner = TimeSpan(_T(2022), _T(2028))
    assert inner in outer


def test_contains_timespan_false_when_inner_extends_beyond():
    outer = TimeSpan(_T(2020), _T(2030))
    assert TimeSpan(_T(2019), _T(2028)) not in outer
    assert TimeSpan(_T(2022), _T(2031)) not in outer


def test_contains_timespan_handles_open_endpoints():
    # outer 가 양쪽 무한 → 어떤 finite span 이든 포함.
    assert TimeSpan(_T(2020), _T(2030)) in TimeSpan(None, None)
    # outer 가 ends_at=None (이후 무한) → starts 만 비교.
    assert TimeSpan(_T(2025), _T(9999)) in TimeSpan(_T(2020), None)
    assert TimeSpan(_T(2019), _T(2030)) not in TimeSpan(_T(2020), None)


def test_contains_instant_true_inside_window():
    span = TimeSpan(_T(2020), _T(2030))
    assert _T(2025) in span
    assert _T(2020) in span  # 경계 포함
    assert _T(2030) in span


def test_contains_instant_false_outside_window():
    span = TimeSpan(_T(2020), _T(2030))
    assert _T(2019) not in span
    assert _T(2031) not in span


def test_starts_before_returns_false_when_self_starts_at_none():
    # 지정 안 함 = "위반 아님" — admin validation 에서 None starts_at 검사 skip 보장.
    assert TimeSpan(None, _T(2030)).starts_before(TimeSpan(_T(2020), _T(2030))) is False


def test_starts_before_returns_true_when_self_explicitly_earlier():
    assert TimeSpan(_T(2019), _T(2030)).starts_before(TimeSpan(_T(2020), _T(2030))) is True
    assert TimeSpan(_T(2020), _T(2030)).starts_before(TimeSpan(_T(2020), _T(2030))) is False


def test_ends_after_returns_false_when_self_ends_at_none():
    assert TimeSpan(_T(2020), None).ends_after(TimeSpan(_T(2020), _T(2030))) is False


def test_ends_after_returns_true_when_self_explicitly_later():
    assert TimeSpan(_T(2020), _T(2031)).ends_after(TimeSpan(_T(2020), _T(2030))) is True
    assert TimeSpan(_T(2020), _T(2030)).ends_after(TimeSpan(_T(2020), _T(2030))) is False
