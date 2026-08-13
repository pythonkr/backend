from datetime import date

import pytest
from django.db.utils import IntegrityError
from internal_api.models import RegistrationDeskConfig

FOREVER_START = RegistrationDeskConfig.DEFAULT_START_DATE
FOREVER_END = RegistrationDeskConfig.DEFAULT_END_DATE


def _config(event, name: str, start: date = FOREVER_START, end: date = FOREVER_END) -> RegistrationDeskConfig:
    return RegistrationDeskConfig.objects.create(name=name, event=event, start_date=start, end_date=end)


def _overlapping(start: date, end: date, exclude_pk=None):
    return RegistrationDeskConfig.objects.filter_active().filter_by_overlap(
        start_date=start, end_date=end, exclude_pk=exclude_pk
    )


def _for_date(on_date: date | None = None) -> RegistrationDeskConfig | None:
    return RegistrationDeskConfig.objects.filter_active().filter_by_date(on_date).first()


@pytest.mark.django_db
def test_period_defaults_to_unbounded_range(desk_event):
    config = RegistrationDeskConfig.objects.create(name="상시", event=desk_event)

    assert (config.start_date, config.end_date) == (date(1, 1, 1), date(9999, 12, 31))


@pytest.mark.django_db
def test_db_constraint_rejects_end_date_before_start_date(desk_event):
    with pytest.raises(IntegrityError):
        _config(desk_event, "역전", date(2026, 8, 16), date(2026, 8, 15))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 8, 15), date(2026, 8, 15)),  # 완전히 동일
        (date(2026, 8, 14), date(2026, 8, 15)),  # 앞쪽 걸침
        (date(2026, 8, 16), date(2026, 8, 20)),  # 뒤쪽 걸침
        (date(2026, 8, 10), date(2026, 8, 20)),  # 포함
        (FOREVER_START, FOREVER_END),  # 무기한
        (FOREVER_START, date(2026, 8, 15)),  # 시작 무제한
        (date(2026, 8, 16), FOREVER_END),  # 종료 무제한
    ],
)
def test_filter_by_overlap_detects_conflicting_period(desk_event, start, end):
    existing = _config(desk_event, "기존", date(2026, 8, 15), date(2026, 8, 16))

    assert _overlapping(start, end).first() == existing


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 8, 17), date(2026, 8, 18)),  # 직후
        (date(2026, 8, 13), date(2026, 8, 14)),  # 직전
        (FOREVER_START, date(2026, 8, 14)),  # 시작 무제한, 겹치지 않음
        (date(2026, 8, 17), FOREVER_END),  # 종료 무제한, 겹치지 않음
    ],
)
def test_filter_by_overlap_allows_disjoint_period(desk_event, start, end):
    _config(desk_event, "기존", date(2026, 8, 15), date(2026, 8, 16))

    assert not _overlapping(start, end).exists()


@pytest.mark.django_db
def test_filter_by_overlap_excludes_given_pk(desk_event):
    config = _config(desk_event, "기존", date(2026, 8, 15), date(2026, 8, 16))

    assert not _overlapping(config.start_date, config.end_date, exclude_pk=config.pk).exists()


@pytest.mark.django_db
def test_filter_by_overlap_ignores_soft_deleted_config(desk_event):
    _config(desk_event, "삭제됨", date(2026, 8, 15), date(2026, 8, 16)).delete()

    assert not _overlapping(date(2026, 8, 15), date(2026, 8, 16)).exists()


@pytest.mark.django_db
def test_filter_by_date_picks_config_covering_the_date(desk_event):
    _config(desk_event, "Day 1", date(2026, 8, 15), date(2026, 8, 15))
    day2 = _config(desk_event, "Day 2", date(2026, 8, 16), date(2026, 8, 16))

    assert _for_date(date(2026, 8, 16)) == day2


@pytest.mark.django_db
def test_filter_by_date_returns_nothing_when_no_config_covers_the_date(desk_event):
    _config(desk_event, "Day 1", date(2026, 8, 15), date(2026, 8, 15))

    assert _for_date(date(2026, 8, 20)) is None


@pytest.mark.django_db
def test_filter_by_date_matches_unbounded_config(desk_event):
    config = _config(desk_event, "상시")

    assert _for_date(date(2026, 8, 20)) == config


@pytest.mark.django_db
def test_filter_by_date_defaults_to_today(desk_event):
    config = _config(desk_event, "상시")

    assert _for_date() == config


@pytest.mark.django_db
def test_prefetch_active_targets_excludes_soft_deleted_categories(desk_event, ticket_product, non_ticket_product):
    config = _config(desk_event, "상시")
    config.categories.add(ticket_product.category, non_ticket_product.category)
    non_ticket_product.category.delete()

    fetched = RegistrationDeskConfig.objects.filter_active().prefetch_active_targets().get(pk=config.pk)

    assert list(fetched.categories.all()) == [ticket_product.category]


@pytest.mark.django_db
def test_ordering_is_by_period(desk_event):
    day2 = _config(desk_event, "Day 2", date(2026, 8, 16), date(2026, 8, 16))
    day1 = _config(desk_event, "Day 1", date(2026, 8, 15), date(2026, 8, 15))

    assert list(RegistrationDeskConfig.objects.filter_active()) == [day1, day2]
