import http
import uuid

import pytest
from admin_api.serializers.event.timetable import timetable_version
from django.urls import reverse
from event.models import Event
from event.presentation.models import Presentation, PresentationType, Room, RoomSchedule
from rest_framework.test import APIClient
from user.models.organization import Organization

TIMETABLE = "v1:admin-event-presentation-timetable-detail"


@pytest.fixture
def event(db) -> Event:
    organization = Organization.objects.create(name="Org")
    return Event.objects.create(name="PyCon", organization=organization)


@pytest.fixture
def presentation(event) -> Presentation:
    ptype = PresentationType.objects.create(name="Talk", event=event)
    return Presentation.objects.create(type=ptype, title="A talk")


@pytest.fixture
def room(event) -> Room:
    return Room.objects.create(event=event, name="Room A")


def _url(event: Event) -> str:
    return reverse(TIMETABLE, args=[event.id])


def _version(event: Event) -> str:
    return timetable_version(event)


def _get(api_client: APIClient, event: Event):
    return api_client.get(_url(event))


def _put(api_client: APIClient, event: Event, payload: dict, if_match: str | None = None):
    extra = {"HTTP_IF_MATCH": if_match} if if_match is not None else {}
    return api_client.put(_url(event), payload, format="json", **extra)


# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_rejected(event):
    response = APIClient().get(_url(event))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


@pytest.mark.django_db
def test_non_superuser_rejected(event, customer_user):
    client = APIClient()
    client.force_authenticate(user=customer_user)
    assert client.get(_url(event)).status_code == http.HTTPStatus.FORBIDDEN


# ---- Read -------------------------------------------------------------------


@pytest.mark.django_db
def test_get_returns_rooms_schedules_and_etag(api_client, event, room, presentation):
    RoomSchedule.objects.create(
        room=room, presentation=presentation, start_at="2026-08-16T10:00:00+09:00", end_at="2026-08-16T11:00:00+09:00"
    )
    response = _get(api_client, event)
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.data["rooms"]) == 1
    assert len(response.data["schedules"]) == 1
    assert "version" not in response.data  # 동시성 토큰은 ETag 헤더로만
    assert response["ETag"].strip('"') == _version(event)


@pytest.mark.django_db
def test_unknown_event_returns_404(api_client):
    assert api_client.get(reverse(TIMETABLE, args=[uuid.uuid4()])).status_code == http.HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_head_returns_etag_without_body(api_client, event, room):
    response = api_client.head(_url(event))
    assert response.status_code == http.HTTPStatus.OK
    assert response["ETag"].strip('"') == _version(event)
    assert not response.content


# ---- Save (op-based partial reflection) -------------------------------------


@pytest.mark.django_db
def test_put_creates_room_and_schedule(api_client, event, presentation):
    payload = {
        "rooms": [{"op": "create", "ref": "new-room", "name_ko": "새방", "name_en": "New", "order": 0}],
        "schedules": [
            {
                "op": "create",
                "room_id": "new-room",  # 같은 요청 방 create 의 ref 로 참조 → 서버가 실제 pk 로 remap
                "presentation": str(presentation.id),
                "start_at": "2026-08-16T10:00:00+09:00",
                "end_at": "2026-08-16T11:00:00+09:00",
            }
        ],
    }
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.OK
    [created_room] = response.data["rooms"]
    [schedule] = response.data["schedules"]
    assert str(schedule["room_id"]) == str(created_room["id"])  # ref → 서버 생성 id 로 해소됨


@pytest.mark.django_db
def test_put_schedule_references_existing_room_by_id(api_client, event, room, presentation):
    payload = {
        "schedules": [
            {
                "op": "create",
                "room_id": str(room.id),  # 기존 방은 실제 id 로 참조
                "presentation": str(presentation.id),
                "start_at": "2026-08-16T10:00:00+09:00",
                "end_at": "2026-08-16T11:00:00+09:00",
            }
        ],
    }
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.OK
    [schedule] = response.data["schedules"]
    assert str(schedule["room_id"]) == str(room.id)


@pytest.mark.django_db
def test_put_unlisted_items_are_untouched(api_client, event):
    keep = Room.objects.create(event=event, name="Keep")
    edit = Room.objects.create(event=event, name="Edit")

    payload = {"rooms": [{"op": "update", "id": str(edit.id), "name_ko": "수정됨"}]}
    response = _put(api_client, event, payload, if_match=_version(event))

    assert response.status_code == http.HTTPStatus.OK
    edit.refresh_from_db()
    assert edit.name_ko == "수정됨"
    assert Room.objects.filter_active().filter(id=keep.id).exists()  # 목록에 없던 방은 그대로
    assert Room.objects.filter_active().filter(event_id=event.id).count() == 2


@pytest.mark.django_db
def test_put_deletes_room_and_its_schedule(api_client, event, room, presentation):
    schedule = RoomSchedule.objects.create(
        room=room, presentation=presentation, start_at="2026-08-16T10:00:00+09:00", end_at="2026-08-16T11:00:00+09:00"
    )
    payload = {
        "rooms": [{"op": "delete", "id": str(room.id)}],
        "schedules": [{"op": "delete", "id": str(schedule.id)}],
    }
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.OK
    assert not Room.objects.filter_active().filter(id=room.id).exists()
    assert not RoomSchedule.objects.filter_active().filter(id=schedule.id).exists()


@pytest.mark.django_db
def test_put_deleting_room_with_remaining_schedule_is_rejected(api_client, event, room, presentation):
    RoomSchedule.objects.create(
        room=room, presentation=presentation, start_at="2026-08-16T10:00:00+09:00", end_at="2026-08-16T11:00:00+09:00"
    )
    # 방만 삭제하고 세션은 남겨두면 고아 세션이 되므로 거부되어야 한다.
    payload = {"rooms": [{"op": "delete", "id": str(room.id)}]}
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert Room.objects.filter_active().filter(id=room.id).exists()  # 롤백됨


@pytest.mark.django_db
def test_put_stale_if_match_returns_412(api_client, event, room):
    stale = _version(event)
    Room.objects.create(event=event, name="Concurrent")  # 그 사이 버전 변경

    response = _put(api_client, event, {"rooms": [{"op": "delete", "id": str(room.id)}]}, if_match=stale)
    assert response.status_code == http.HTTPStatus.PRECONDITION_FAILED
    assert len(response.data["rooms"]) == 2  # 현재 서버 상태를 함께 반환
    assert Room.objects.filter_active().filter(id=room.id).exists()  # 저장 미적용


@pytest.mark.django_db
def test_put_conflict_returns_400_and_rolls_back(api_client, event, room, presentation):
    overlapping = {
        "schedules": [
            {
                "op": "create",
                "room_id": str(room.id),
                "presentation": str(presentation.id),
                "start_at": "2026-08-16T10:00:00+09:00",
                "end_at": "2026-08-16T11:00:00+09:00",
            },
            {
                "op": "create",
                "room_id": str(room.id),
                "presentation": str(presentation.id),
                "start_at": "2026-08-16T10:30:00+09:00",
                "end_at": "2026-08-16T11:30:00+09:00",
            },
        ],
    }
    response = _put(api_client, event, overlapping, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert RoomSchedule.objects.filter_active().filter(room__event_id=event.id).count() == 0  # 롤백됨


@pytest.mark.django_db
def test_put_update_missing_instance_returns_400(api_client, event):
    payload = {"rooms": [{"op": "update", "id": str(uuid.uuid4()), "name_ko": "없음"}]}
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_put_cannot_touch_other_event_room(api_client, event):
    # 다른 event 의 방 id 로 update 를 시도해도 이 event 스코프 밖이라 400, 대상은 그대로여야 한다.
    other_event = Event.objects.create(name="Other", organization=event.organization)
    foreign = Room.objects.create(event=other_event, name="Foreign")

    payload = {"rooms": [{"op": "update", "id": str(foreign.id), "name_ko": "침범"}]}
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    foreign.refresh_from_db()
    assert foreign.name_ko == "Foreign"  # 변경 안 됨


@pytest.mark.django_db
def test_put_schedule_with_unknown_room_ref_returns_400(api_client, event, presentation):
    payload = {
        "schedules": [
            {
                "op": "create",
                "room_id": "no-such-ref",  # 존재하는 방 id 도, 이번 요청의 방 ref 도 아님
                "presentation": str(presentation.id),
                "start_at": "2026-08-16T10:00:00+09:00",
                "end_at": "2026-08-16T11:00:00+09:00",
            }
        ],
    }
    response = _put(api_client, event, payload, if_match=_version(event))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- Version token ----------------------------------------------------------


@pytest.mark.django_db
def test_version_changes_on_delete(event):
    room = Room.objects.create(event=event, name="R")
    before = _version(event)
    room.delete()  # soft delete (updated_at 은 안 오르지만 count 가 바뀜)
    assert _version(event) != before
