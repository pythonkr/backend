from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.util.dateutil import any_to_datetime
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationSpeaker,
    PresentationType,
    Room,
    RoomSchedule,
)
from file.models import PublicFile
from rest_framework import serializers
from user.models import UserExt


class PresentationTypeAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationType
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en")


class PresentationCategoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = COMMON_ADMIN_FIELDS + ("type", "name_ko", "name_en")


class PresentationAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=PresentationCategory.objects.filter_active()
    )
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.filter_active(), allow_null=True, required=False
    )

    class Meta:
        model = Presentation
        fields = COMMON_ADMIN_FIELDS + (
            "type",
            "categories",
            "title_ko",
            "title_en",
            "summary_ko",
            "summary_en",
            "slideshow_url",
            "image",
            "description_ko",
            "description_en",
        )

    def validate(self, attrs: dict) -> dict:
        type = attrs.get("type", getattr(self.instance, "type", None))
        categories = attrs.get("categories", getattr(self.instance, "categories", []))

        if type and categories:
            if not all(category.type == type for category in categories):
                raise serializers.ValidationError("All categories must belong to the same type.")

        return super().validate(attrs)


class PresentationSpeakerAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=UserExt.objects.filter(is_active=True))
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.filter_active(), allow_null=True, required=False
    )

    class Meta:
        model = PresentationSpeaker
        fields = COMMON_ADMIN_FIELDS + ("presentation", "user", "image", "biography_ko", "biography_en")


class RoomScheduleAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = RoomSchedule
        fields = ("room", "start_at", "end_at", "presentation")

    def validate(self, attrs: dict) -> dict:
        start_at = any_to_datetime(attrs.get("start_at", getattr(self.instance, "start_at", None)))
        end_at = any_to_datetime(attrs.get("end_at", getattr(self.instance, "end_at", None)))
        room: Room | None = attrs.get("room", getattr(self.instance, "room", None))

        if start_at and end_at:
            if start_at >= end_at:
                raise serializers.ValidationError({"start_at": "시작 시간은 종료 시간보다 전이어야 합니다."})

            qs = RoomSchedule.objects.filter_active().filter_conflict(room, start_at, end_at)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if room and qs.exists():
                raise serializers.ValidationError({"room": "해당 시간에 이미 발표가 진행 중입니다."})

        return super().validate(attrs)


class RoomAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en")
