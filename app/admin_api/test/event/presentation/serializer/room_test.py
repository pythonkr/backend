from datetime import datetime

import pytest
from admin_api.serializers.event.presentation import RoomScheduleAdminSerializer
from event.models import Event
from event.presentation.models import Presentation, PresentationType, Room, RoomSchedule
from user.models.organization import Organization


@pytest.mark.django_db
def test_room_schedule_serializer_should_validate_reverse_start_end_time() -> None:
    # Given: 발표 장소와 발표 객체 존재
    organization = Organization.objects.create(name="Test Organization")
    event = Event.objects.create(name="Test Event", organization=organization)
    room = Room.objects.create(event=event, name="Test Room")

    presentation_type = PresentationType.objects.create(name="Test Type", event=event)
    presentation = Presentation.objects.create(type=presentation_type, title="Test Presentation")

    # When: 시작 시각을 종료 시각 이후로 입력한 경우 (2023년 10월 1일 10시부터 9시까지)
    serializer = RoomScheduleAdminSerializer(
        data={
            "room": room.pk,
            "presentation": presentation.pk,
            "start_at": "2023-10-01T10:00:00",
            "end_at": "2023-10-01T09:00:00",
        }
    )

    # Then: 유효성 검사에서 실패해야 한다.
    assert not serializer.is_valid()

    # And: 에러 메시지가 올바르게 설정되어야 한다.
    assert "start_at" in serializer.errors
    assert serializer.errors["start_at"] == ["시작 시간은 종료 시간보다 전이어야 합니다."]


@pytest.mark.django_db
def test_room_schedule_serializer_should_validate_reverse_start_end_time_with_instance() -> None:
    # Given: 발표 장소와 발표 객체 존재
    organization = Organization.objects.create(name="Test Organization")
    event = Event.objects.create(name="Test Event", organization=organization)
    room = Room.objects.create(event=event, name="Test Room")

    presentation_type = PresentationType.objects.create(name="Test Type", event=event)
    presentation = Presentation.objects.create(type=presentation_type, title="Test Presentation")

    # And: RoomSchedule 인스턴스도 존재 (2023년 10월 1일 9시부터 10시까지)
    room_schedule = RoomSchedule.objects.create(
        room=room,
        presentation=presentation,
        start_at="2023-10-01T09:00:00",
        end_at="2023-10-01T10:00:00",
    )

    # When: 시작 시각을 종료 시각 이후로 수정하는 경우 (2023년 10월 1일 11시부터 10시까지)
    serializer = RoomScheduleAdminSerializer(
        instance=room_schedule,
        data={"start_at": "2023-10-01T10:00:00"},
        partial=True,
    )

    # Then: 유효성 검사에서 실패해야 한다.
    assert not serializer.is_valid()

    # And: 에러 메시지가 올바르게 설정되어야 한다.
    assert "start_at" in serializer.errors
    assert serializer.errors["start_at"] == ["시작 시간은 종료 시간보다 전이어야 합니다."]


@pytest.mark.parametrize(
    argnames=["start_at", "end_at", "is_valid"],
    argvalues=[
        # 유효한 경우
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 13, 0), True),
        (datetime(2023, 10, 1, 14, 0), datetime(2023, 10, 1, 15, 0), True),
        # 유효하지 않은 경우
        (datetime(2023, 10, 1, 13, 0), datetime(2023, 10, 1, 14, 0), False),
        (datetime(2023, 10, 1, 13, 20), datetime(2023, 10, 1, 13, 40), False),
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 15, 0), False),
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 13, 30), False),
        (datetime(2023, 10, 1, 13, 30), datetime(2023, 10, 1, 15, 0), False),
    ],
)
@pytest.mark.django_db
def test_room_schedule_serializer_should_validate_conflict_start_end_time(
    start_at: datetime, end_at: datetime, is_valid: bool
) -> None:
    # Given: 발표 장소와 발표 객체 2개 존재
    organization = Organization.objects.create(name="Test Organization")
    event = Event.objects.create(name="Test Event", organization=organization)
    room = Room.objects.create(event=event, name="Test Room")

    presentation_type = PresentationType.objects.create(name="Test Type", event=event)
    presentation_1 = Presentation.objects.create(type=presentation_type, title="Test Presentation 1")
    presentation_2 = Presentation.objects.create(type=presentation_type, title="Test Presentation 2")

    # And: 이미 room에 등록된 RoomSchedule 인스턴스 존재 (2023년 10월 1일 13시부터 14시까지)
    RoomSchedule.objects.create(
        room=room,
        presentation=presentation_1,
        start_at=datetime(2023, 10, 1, 13, 0),
        end_at=datetime(2023, 10, 1, 14, 0),
    )

    # When: presentation_1과 겹치는 시간에 새로운 RoomSchedule을 생성하려는 경우
    serializer = RoomScheduleAdminSerializer(
        data={
            "room": room.pk,
            "presentation": presentation_2.pk,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        }
    )

    # Then: 유효성 검사에서 실패해야 한다.
    assert serializer.is_valid() == is_valid

    # And: 유효하지 않은 경우, 에러 메시지가 올바르게 설정되어야 한다.
    if not is_valid:
        assert "room" in serializer.errors
        assert serializer.errors["room"] == ["해당 시간에 이미 발표가 진행 중입니다."]


@pytest.mark.parametrize(
    argnames=["start_at", "end_at", "is_valid"],
    argvalues=[
        # 유효한 경우
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 13, 0), True),
        (datetime(2023, 10, 1, 14, 0), datetime(2023, 10, 1, 15, 0), True),
        # 유효하지 않은 경우
        (datetime(2023, 10, 1, 13, 0), datetime(2023, 10, 1, 14, 0), False),
        (datetime(2023, 10, 1, 13, 20), datetime(2023, 10, 1, 13, 40), False),
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 15, 0), False),
        (datetime(2023, 10, 1, 12, 0), datetime(2023, 10, 1, 13, 30), False),
        (datetime(2023, 10, 1, 13, 30), datetime(2023, 10, 1, 15, 0), False),
    ],
)
@pytest.mark.django_db
def test_room_schedule_serializer_should_validate_conflict_start_end_time_with_instance(
    start_at: datetime, end_at: datetime, is_valid: bool
) -> None:
    # Given: 발표 장소와 발표 객체 2개 존재
    organization = Organization.objects.create(name="Test Organization")
    event = Event.objects.create(name="Test Event", organization=organization)
    room = Room.objects.create(event=event, name="Test Room")

    presentation_type = PresentationType.objects.create(name="Test Type", event=event)
    presentation_1 = Presentation.objects.create(type=presentation_type, title="Test Presentation 1")
    presentation_2 = Presentation.objects.create(type=presentation_type, title="Test Presentation 2")

    # And: 이미 room에 등록된 RoomSchedule 인스턴스 존재 (2023년 10월 1일 13시부터 14시까지)
    RoomSchedule.objects.create(
        room=room,
        presentation=presentation_1,
        start_at=datetime(2023, 10, 1, 13, 0),
        end_at=datetime(2023, 10, 1, 14, 0),
    )

    # And: RoomSchedule 인스턴스도 존재 (2023년 10월 1일 14시부터 15시까지)
    room_schedule = RoomSchedule.objects.create(
        room=room,
        presentation=presentation_2,
        start_at=datetime(2023, 10, 1, 14, 0),
        end_at=datetime(2023, 10, 1, 15, 0),
    )

    # When: presentation_1과 겹치는 시간에 새로운 RoomSchedule을 생성하려는 경우
    serializer = RoomScheduleAdminSerializer(
        instance=room_schedule,
        data={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        partial=True,
    )

    # Then: 유효성 검사에서 실패해야 한다.
    assert serializer.is_valid() == is_valid, serializer.errors

    # And: 유효하지 않은 경우, 에러 메시지가 올바르게 설정되어야 한다.
    if not is_valid:
        assert "room" in serializer.errors
        assert serializer.errors["room"] == ["해당 시간에 이미 발표가 진행 중입니다."]
