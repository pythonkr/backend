from event.presentation.models import (
    CallForPresentationSchedule,
    Presentation,
    PresentationCategory,
    PresentationSpeaker,
    RoomSchedule,
)
from rest_framework import serializers


class PresentationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = ("id", "name")


class PresentationSpeakerSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "nickname", "biography", "image")


class RoomScheduleSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source="room.name", read_only=True)
    event_id = serializers.IntegerField(source="room.event.id", read_only=True)
    event_name = serializers.CharField(source="room.event.name", read_only=True)

    class Meta:
        model = RoomSchedule
        fields = ("id", "room_name", "event_id", "event_name", "start_at", "end_at")


class CallForPresentationScheduleSerializer(serializers.ModelSerializer):
    presentation_type_name = serializers.CharField(source="presentation_type.name", read_only=True)

    class Meta:
        model = CallForPresentationSchedule
        fields = ("id", "presentation_type_name", "start_at", "end_at", "next_call_for_presentation_schedule")


class PresentationSerializer(serializers.ModelSerializer):
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)
    categories = PresentationCategorySerializer(many=True, read_only=True)
    speakers = PresentationSpeakerSerializer(many=True, read_only=True)
    room_schedules = RoomScheduleSerializer(source="room_schedules_set", many=True, read_only=True)
    call_for_presentation_schedules = CallForPresentationScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = (
            "id",
            "title",
            "summary",
            "description",
            "image",
            "categories",
            "speakers",
            "room_schedules",
            "call_for_presentation_schedules",
        )
