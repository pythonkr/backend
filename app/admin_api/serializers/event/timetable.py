from __future__ import annotations

import hashlib
from collections import defaultdict

from core.serializer.operation_serializer import Operation, OperationSerializer
from core.util.dateutil import any_to_datetime
from django.db import transaction
from django.db.models import Count, Max
from event.models import Event
from event.presentation.models import Presentation, Room, RoomSchedule
from rest_framework import serializers


class RoomOperationAdminSerializer(OperationSerializer, serializers.ModelSerializer):
    # 같은 요청의 신규 스케줄이 이 방을 참조하기 위한 요청 스코프 토큰(저장 안 함, 부모 save 에서 실제 pk 로 remap).
    ref = serializers.CharField(write_only=True, required=False)

    class Meta(OperationSerializer.Meta):
        model = Room
        fields = OperationSerializer.Meta.fields + ("ref", "name_ko", "name_en", "order")

    def get_operation_queryset(self):  # update/delete 는 이 event 하위 방으로 한정
        return Room.objects.filter_active().filter(event=self.context["event"])


class RoomScheduleOperationAdminSerializer(OperationSerializer, serializers.ModelSerializer):
    # room_id: 읽기는 방 pk 를 그대로 노출, 쓰기는 기존 방 id 또는 같은 요청 방 create 의 ref → 부모 save 에서 해소.
    room_id = serializers.CharField()
    presentation = serializers.PrimaryKeyRelatedField(queryset=Presentation.objects.filter_active())

    class Meta(OperationSerializer.Meta):
        model = RoomSchedule
        fields = OperationSerializer.Meta.fields + ("room_id", "start_at", "end_at", "presentation")

    def get_operation_queryset(self):  # update/delete 는 이 event 하위 스케줄로 한정
        return RoomSchedule.objects.filter_active().filter(room__event=self.context["event"])

    def validate(self, attrs: dict) -> dict:
        start = any_to_datetime(attrs.get("start_at", getattr(self.instance, "start_at", None)))
        end = any_to_datetime(attrs.get("end_at", getattr(self.instance, "end_at", None)))
        if start and end and start >= end:
            raise serializers.ValidationError({"start_at": "시작 시간은 종료 시간보다 전이어야 합니다."})
        return attrs


def timetable_version(event: Event) -> str:
    rooms = Room.objects.filter_active().filter(event_id=event.id).aggregate(c=Count("id"), m=Max("updated_at"))
    scheds = (
        RoomSchedule.objects.filter_active()
        .filter(room__event_id=event.id)
        .aggregate(c=Count("id"), m=Max("updated_at"))
    )
    raw = f"{rooms['c']}|{rooms['m']}|{scheds['c']}|{scheds['m']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class TimetableAdminSerializer(serializers.Serializer):
    rooms = RoomOperationAdminSerializer(many=True, required=False)
    schedules = RoomScheduleOperationAdminSerializer(many=True, required=False)

    def to_representation(self, event: Event) -> dict:
        return super().to_representation(
            {
                "rooms": Room.objects.filter_active().filter(event_id=event.id).order_by("order", "pk"),
                "schedules": (
                    RoomSchedule.objects.filter_active().filter(room__event_id=event.id).order_by("start_at", "pk")
                ),
            }
        )

    @transaction.atomic
    def save(self, **kwargs) -> Event:
        event = self.context["event"]
        room_ops = self.validated_data.get("rooms", [])
        room_results = self.fields["rooms"].apply(room_ops, event=event)

        ref_to_room = {
            op["ref"]: room
            for op, room in zip(room_ops, room_results)
            if op["op"] == Operation.CREATE and op.get("ref") is not None
        }
        rooms_by_id = {str(room.id): room for room in Room.objects.filter_active().filter(event_id=event.id)}

        schedule_ops = self.validated_data.get("schedules", [])
        for attrs in schedule_ops:
            if not (room_key := attrs.get("room_id")):
                continue
            if not (room := ref_to_room.get(room_key) or rooms_by_id.get(room_key)):
                raise serializers.ValidationError({"schedules": "이벤트에 속한 활성 발표장이 아닙니다."})
            attrs["room_id"] = room.id
        self.fields["schedules"].apply(schedule_ops)

        rows = (
            RoomSchedule.objects.filter_active()
            .filter(room__event_id=event.id)
            .order_by("room_id", "start_at")
            .values("room_id", "room__deleted_at", "start_at", "end_at")
        )
        by_room: dict = defaultdict(list)
        for row in rows:
            if row["room__deleted_at"] is not None:
                raise serializers.ValidationError({"schedules": "삭제된 발표장을 참조하는 세션이 남아 있습니다."})
            by_room[row["room_id"]].append(row)
        for items in by_room.values():
            for prev, cur in zip(items, items[1:]):
                if cur["start_at"] < prev["end_at"]:
                    raise serializers.ValidationError({"schedules": "같은 발표장에 시간이 겹치는 세션이 있습니다."})

        return event
