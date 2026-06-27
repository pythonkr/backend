from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.models import Event
from rest_framework import serializers


class EventAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = COMMON_ADMIN_FIELDS + (
            "organization",
            "name_ko",
            "name_en",
            "event_start_at",
            "event_end_at",
            "stats_start_date",
            "stats_end_date",
        )

    def validate(self, attrs: dict) -> dict:
        merged = {**attrs}
        for field in ("stats_start_date", "stats_end_date"):
            merged.setdefault(field, getattr(self.instance, field, None))
        start, end = merged["stats_start_date"], merged["stats_end_date"]
        if start and end and start > end:
            raise serializers.ValidationError({"stats_end_date": "통계 종료일은 시작일보다 이전일 수 없습니다."})
        return attrs
