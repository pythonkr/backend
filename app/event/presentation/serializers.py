from typing import Any

from event.presentation.models import (
    CallForPresentationSchedule,
    Presentation,
    PresentationBookmark,
    PresentationCategory,
    PresentationSpeaker,
    PresentationType,
    RoomSchedule,
)
from event.serializers import EventSerializer
from rest_framework import exceptions, serializers


class NotFoundPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def fail(self, key, **kwargs):
        if key == "does_not_exist":
            raise exceptions.NotFound("해당 세션 정보가 없습니다.")
        super().fail(key, **kwargs)


class PresentationBookmarkRequestSerializer(serializers.Serializer):
    presentation_id = NotFoundPrimaryKeyRelatedField(
        queryset=Presentation.objects.filter(deleted_at__isnull=True),
        source="presentation",
    )

    def create(self, validated_data: Any) -> tuple[PresentationBookmark, bool]:
        validated_data["user"] = self.context["request"].user
        return PresentationBookmark.objects.get_or_create(**validated_data)


class PresentationBookmarkListResponseSerializer(serializers.Serializer):
    presentation_ids = serializers.ListField(child=serializers.UUIDField())


class PresentationBookmarkResponseSerializer(serializers.Serializer):
    presentation_id = serializers.UUIDField()


class PresentationTypeSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)

    class Meta:
        model = PresentationType
        fields = ("id", "name", "event")


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
    room_order = serializers.IntegerField(source="room.order", read_only=True)

    class Meta:
        model = RoomSchedule
        fields = ("id", "room_name", "room_order", "start_at", "end_at")


class CallForPresentationScheduleSerializer(serializers.ModelSerializer):
    presentation_type_name = serializers.CharField(source="presentation_type.name", read_only=True)

    class Meta:
        model = CallForPresentationSchedule
        fields = ("id", "presentation_type_name", "start_at", "end_at", "next_call_for_presentation_schedule")


class PresentationSerializer(serializers.ModelSerializer):
    presentation_type = PresentationTypeSerializer(source="type", read_only=True)
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)
    categories = PresentationCategorySerializer(many=True, read_only=True, source="active_categories")
    speakers = PresentationSpeakerSerializer(many=True, read_only=True, source="active_speakers")
    room_schedules = RoomScheduleSerializer(many=True, read_only=True, source="active_room_schedules")
    call_for_presentation_schedules = CallForPresentationScheduleSerializer(many=True, read_only=True)
    public_slideshow_file = serializers.FileField(source="public_slideshow_file.file", read_only=True, allow_null=True)

    class Meta:
        model = Presentation
        fields = (
            "id",
            "presentation_type",
            "title",
            "summary",
            "description",
            "slideshow_url",
            "public_slideshow_file",
            "image",
            "categories",
            "speakers",
            "room_schedules",
            "call_for_presentation_schedules",
        )
