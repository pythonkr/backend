import pytest
from admin_api.filtersets.event.presentation import (
    PresentationAdminFilterSet,
    RoomScheduleAdminFilterSet,
)
from event.models import Event
from event.presentation.models import Presentation, PresentationType, Room, RoomSchedule
from user.models.organization import Organization


@pytest.mark.django_db
def test_presentation_admin_filterset_filters_by_event() -> None:
    # Given: 서로 다른 이벤트에 속한 발표 2개
    organization = Organization.objects.create(name="Test Organization")
    event_a = Event.objects.create(name="Event A", organization=organization)
    event_b = Event.objects.create(name="Event B", organization=organization)

    type_a = PresentationType.objects.create(name="Type A", event=event_a)
    type_b = PresentationType.objects.create(name="Type B", event=event_b)
    presentation_a = Presentation.objects.create(type=type_a, title="A")
    Presentation.objects.create(type=type_b, title="B")

    # When: event_a 로 필터링
    filterset = PresentationAdminFilterSet({"event": str(event_a.pk)}, queryset=Presentation.objects.all())

    # Then: event_a 의 발표만 반환
    assert list(filterset.qs) == [presentation_a]


@pytest.mark.django_db
def test_room_schedule_admin_filterset_filters_by_event() -> None:
    # Given: 서로 다른 이벤트의 방/발표에 속한 스케줄 2개
    organization = Organization.objects.create(name="Test Organization")
    event_a = Event.objects.create(name="Event A", organization=organization)
    event_b = Event.objects.create(name="Event B", organization=organization)

    room_a = Room.objects.create(event=event_a, name="Room A")
    room_b = Room.objects.create(event=event_b, name="Room B")

    type_a = PresentationType.objects.create(name="Type A", event=event_a)
    type_b = PresentationType.objects.create(name="Type B", event=event_b)
    presentation_a = Presentation.objects.create(type=type_a, title="A")
    presentation_b = Presentation.objects.create(type=type_b, title="B")

    schedule_a = RoomSchedule.objects.create(
        room=room_a,
        presentation=presentation_a,
        start_at="2026-08-16T10:00:00+09:00",
        end_at="2026-08-16T11:00:00+09:00",
    )
    RoomSchedule.objects.create(
        room=room_b,
        presentation=presentation_b,
        start_at="2026-08-16T10:00:00+09:00",
        end_at="2026-08-16T11:00:00+09:00",
    )

    # When: event_a 로 필터링
    filterset = RoomScheduleAdminFilterSet({"event": str(event_a.pk)}, queryset=RoomSchedule.objects.all())

    # Then: event_a 의 스케줄만 반환
    assert list(filterset.qs) == [schedule_a]
