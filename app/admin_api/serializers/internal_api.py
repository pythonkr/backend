from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.models import Event
from internal_api.models import RegistrationDeskConfig
from rest_framework import serializers
from shop.product.models import Category


class RegistrationDeskConfigAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.filter_active())
    logo_url = serializers.CharField(source="event.logo.file.url", read_only=True, allow_null=True)

    categories = serializers.PrimaryKeyRelatedField(
        many=True, allow_empty=False, queryset=Category.objects.filter_active()
    )

    class Meta:
        model = RegistrationDeskConfig
        fields = COMMON_ADMIN_FIELDS + (
            "name",
            "event",
            "start_date",
            "end_date",
            "logo_url",
            "categories",
        )

    def validate(self, attrs: dict) -> dict:
        merged = {**attrs}
        for field, fallback in (
            ("start_date", RegistrationDeskConfig.DEFAULT_START_DATE),
            ("end_date", RegistrationDeskConfig.DEFAULT_END_DATE),
        ):
            if merged.get(field) is None:
                merged[field] = getattr(self.instance, field, None) or fallback

        start, end = merged["start_date"], merged["end_date"]
        if start > end:
            raise serializers.ValidationError({"end_date": "종료일은 시작일보다 빠를 수 없습니다."})

        # 행사 없는 공용 카테고리(굿즈 등)는 어느 설정에서나 허용.
        event = attrs.get("event") or getattr(self.instance, "event", None)
        categories = attrs.get("categories", [] if self.instance is None else list(self.instance.categories.all()))
        if event and (mismatched := [c.name for c in categories if c.event_id not in (None, event.id)]):
            joined = ", ".join(mismatched)
            raise serializers.ValidationError({"categories": f"설정의 행사와 다른 행사의 카테고리입니다: {joined}"})

        if conflict := (
            RegistrationDeskConfig.objects.filter_active()
            .filter_by_overlap(start_date=start, end_date=end, exclude_pk=self.instance.pk if self.instance else None)
            .first()
        ):
            raise serializers.ValidationError({"start_date": f"적용 기간이 «{conflict.name}» 과(와) 겹칩니다."})

        return attrs
