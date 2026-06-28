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
            "logo",
            "name_ko",
            "name_en",
            "event_start_at",
            "event_end_at",
            "stats_start_date",
            "stats_end_date",
        )

    DATE_ORDER_PAIRS = (
        ("event_start_at", "event_end_at", "event의 종료 날짜는 시작 날짜보다 이전일 수 없습니다."),
        ("stats_start_date", "stats_end_date", "통계 종료일은 시작일보다 이전일 수 없습니다."),
    )

    def validate(self, attrs: dict) -> dict:
        merged = {**attrs}
        for start_field, end_field, msg in self.DATE_ORDER_PAIRS:
            start = merged.setdefault(start_field, getattr(self.instance, start_field, None))
            end = merged.setdefault(end_field, getattr(self.instance, end_field, None))
            if start and end and start > end:
                raise serializers.ValidationError({end_field: msg})
        return attrs
