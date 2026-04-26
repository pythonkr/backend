from contextlib import suppress
from typing import Any

from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from notification.models import (
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationTemplate,
    NHNCloudSMSNotificationTemplate,
)
from notification.models.base import (
    NotificationHistoryBase,
    NotificationStatus,
    NotificationTemplateBase,
    UnhandledVariableHandling,
)
from rest_framework import serializers


class NotificationHistoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer):
    template = serializers.UUIDField(source="template_id", read_only=True)
    template_code = serializers.CharField(read_only=True)
    send_to = serializers.CharField(read_only=True)
    context = serializers.JSONField(read_only=True)
    status = serializers.ChoiceField(choices=NotificationStatus.choices)

    def validate_status(self, value: str) -> str:
        if not self.instance:
            return value

        if not (self.instance.status == NotificationStatus.SENDING and value == NotificationStatus.FAILED):
            raise serializers.ValidationError(
                f"상태 변경은 SENDING → FAILED만 가능해요. ({self.instance.status} → {value})"
            )
        return value

    def update(self, instance: NotificationHistoryBase, validated_data: dict[str, Any]) -> NotificationHistoryBase:
        instance.status = validated_data["status"]
        instance.save(update_fields=["status"])
        return instance


class _NotiTemplateAdminSerializerBase(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    template_variables = serializers.SerializerMethodField()

    def get_template_variables(self, obj: NotificationTemplateBase) -> list[str]:
        return sorted(obj.template_variables)

    def render(self, context: dict[str, Any]) -> str:
        return self.instance.render_as_html(
            context=context,
            undefined_variable_handling=UnhandledVariableHandling.RANDOM,
        )

    def create_history(self, send_to: str, context: dict[str, Any]) -> NotificationHistoryBase:
        history = self.instance.histories.create(send_to=send_to, context=context)
        with suppress(Exception):
            history.send()
        return history


class EmailNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    class Meta:
        model = EmailNotificationTemplate
        fields = COMMON_ADMIN_FIELDS + ("code", "title", "description", "data", "from_address", "template_variables")


class NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    class Meta:
        model = NHNCloudKakaoAlimTalkNotificationTemplate
        fields = COMMON_ADMIN_FIELDS + ("code", "title", "description", "data", "sender_key", "template_variables")
        read_only_fields = fields  # NHN Cloud Console에서 관리되므로 모든 필드 read-only.


class NHNCloudSMSNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    class Meta:
        model = NHNCloudSMSNotificationTemplate
        fields = COMMON_ADMIN_FIELDS + ("code", "title", "description", "data", "from_no", "template_variables")


class NotificationTemplateRenderRequestAdminSerializer(serializers.Serializer):
    context = serializers.JSONField(required=False, default=dict)


class NotificationHistoryCreateRequestAdminSerializer(serializers.Serializer):
    send_to = serializers.CharField(max_length=256)
    context = serializers.JSONField(required=False, default=dict)
