from datetime import date

from admin_api.serializers.event.event import EventAdminSerializer
from model_bakery import baker


def test_admin_serializer_exposes_stats_period_fields():
    assert {"stats_start_date", "stats_end_date"} <= set(EventAdminSerializer().fields)


def test_admin_serializer_accepts_valid_stats_period(db):
    event = baker.make("event.Event")
    serializer = EventAdminSerializer(
        instance=event,
        data={"stats_start_date": "2026-08-14", "stats_end_date": "2026-08-16"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors


def test_admin_serializer_rejects_inverted_stats_period(db):
    event = baker.make("event.Event", stats_start_date=date(2026, 8, 1))
    serializer = EventAdminSerializer(
        instance=event,
        data={"stats_start_date": "2026-08-16", "stats_end_date": "2026-08-14"},
        partial=True,
    )
    assert not serializer.is_valid()
    assert "stats_end_date" in serializer.errors
