from typing import Any

from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from notification.models import (
    EmailNotificationHistory,
    EmailNotificationHistorySentTo,
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationHistory,
    NHNCloudKakaoAlimTalkNotificationHistorySentTo,
    NHNCloudKakaoAlimTalkNotificationTemplate,
    NHNCloudSMSNotificationHistory,
    NHNCloudSMSNotificationHistorySentTo,
    NHNCloudSMSNotificationTemplate,
)
from notification.models.base import (
    NotificationHistoryBase,
    NotificationStatus,
    NotificationTemplateBase,
    UnhandledVariableHandling,
)
from rest_framework import serializers

# ---- SentTo nested ----------------------------------------------------------


class _NotiHistorySentToAdminSerializerBase(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        fields = COMMON_ADMIN_FIELDS + ("recipient", "context", "status", "failure_reason")
        read_only_fields = (*COMMON_ADMIN_FIELDS, "status", "failure_reason")


class EmailNotificationHistorySentToAdminSerializer(_NotiHistorySentToAdminSerializerBase):
    class Meta(_NotiHistorySentToAdminSerializerBase.Meta):
        model = EmailNotificationHistorySentTo


class NHNCloudSMSNotificationHistorySentToAdminSerializer(_NotiHistorySentToAdminSerializerBase):
    class Meta(_NotiHistorySentToAdminSerializerBase.Meta):
        model = NHNCloudSMSNotificationHistorySentTo


class NHNCloudKakaoAlimTalkNotificationHistorySentToAdminSerializer(_NotiHistorySentToAdminSerializerBase):
    class Meta(_NotiHistorySentToAdminSerializerBase.Meta):
        model = NHNCloudKakaoAlimTalkNotificationHistorySentTo


# ---- History --------------------------------------------------------------


class _NotiHistoryAdminSerializerBase(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class SummarySerializer(serializers.Serializer):
        created = serializers.IntegerField(read_only=True)
        sending = serializers.IntegerField(read_only=True)
        sent = serializers.IntegerField(read_only=True)
        failed = serializers.IntegerField(read_only=True)

    template_code = serializers.CharField(read_only=True)
    sent_to_status_summary = SummarySerializer(read_only=True)

    class Meta:
        fields = COMMON_ADMIN_FIELDS + (
            "template",
            "template_code",
            "template_data",
            "sent_from",
            "sent_to_list",
            "sent_to_status_summary",
        )

    def create(self, validated_data: dict[str, Any]) -> NotificationHistoryBase:
        # template이 명시되지 않은 templateless 경로면 transient (unsaved) template_class 인스턴스로 폴백.
        # Kakao는 template이 required + template_data/sent_from이 read-only라 or 우측이 실행되지 않음.
        template = validated_data.get("template") or self.Meta.model.template_class(
            data=validated_data.get("template_data") or "",
            sent_from=validated_data.get("sent_from") or "",
        )
        history = self.Meta.model.objects.create_for_recipients(
            template=template,
            recipients=validated_data["sent_to_list"],
        )
        history.send()
        history.refresh_from_db()
        return history

    def retry(self, statuses: list[NotificationStatus], sent_to_id: str | None = None) -> None:
        if not (self.instance and self.instance.pk):
            raise ValueError("인스턴스가 저장된 후에만 retry할 수 있습니다.")

        self.instance.retry(sent_to_id=sent_to_id, statuses=statuses)
        self.instance.refresh_from_db()


class EmailNotificationHistoryAdminSerializer(_NotiHistoryAdminSerializerBase):
    template = serializers.PrimaryKeyRelatedField(
        queryset=EmailNotificationTemplate.objects.filter_active(),
        required=False,
        allow_null=True,
    )
    # 모델은 base에서 max_length=256 CharField — Email 채널은 EmailField 검증 + RFC 길이 254 적용.
    sent_from = serializers.EmailField(max_length=254, required=False, default="")
    sent_to_list = EmailNotificationHistorySentToAdminSerializer(many=True, allow_empty=False)

    class Meta(_NotiHistoryAdminSerializerBase.Meta):
        model = EmailNotificationHistory
        extra_kwargs = {"template_data": {"required": False, "default": ""}}


class NHNCloudSMSNotificationHistoryAdminSerializer(_NotiHistoryAdminSerializerBase):
    template = serializers.PrimaryKeyRelatedField(
        queryset=NHNCloudSMSNotificationTemplate.objects.filter_active(),
        required=False,
        allow_null=True,
    )
    # SMS 발신번호는 최대 13자리.
    sent_from = serializers.CharField(max_length=13, required=False, default="")
    sent_to_list = NHNCloudSMSNotificationHistorySentToAdminSerializer(many=True, allow_empty=False)

    class Meta(_NotiHistoryAdminSerializerBase.Meta):
        model = NHNCloudSMSNotificationHistory
        extra_kwargs = {"template_data": {"required": False, "default": ""}}


class NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer(_NotiHistoryAdminSerializerBase):
    template = serializers.PrimaryKeyRelatedField(
        queryset=NHNCloudKakaoAlimTalkNotificationTemplate.objects.filter_active(),
        required=True,  # Kakao 알림톡은 템플릿 필수
    )
    sent_to_list = NHNCloudKakaoAlimTalkNotificationHistorySentToAdminSerializer(many=True, allow_empty=False)

    class Meta(_NotiHistoryAdminSerializerBase.Meta):
        model = NHNCloudKakaoAlimTalkNotificationHistory
        read_only_fields = ("template_data", "sent_from")  # template에서 snapshot되므로 입력 불가


# ---- Template ---------------------------------------------------------------


class _NotiTemplateAdminSerializerBase(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    template_variables = serializers.SerializerMethodField()

    class Meta:
        fields = COMMON_ADMIN_FIELDS + ("code", "title", "description", "data", "sent_from", "template_variables")

    def get_template_variables(self, obj: NotificationTemplateBase) -> list[str]:
        return sorted(obj.template_variables)

    def render(self, context: dict[str, Any]) -> str:
        return self.instance.build_preview_sent_to(context).render_as_html(undef_var=UnhandledVariableHandling.RANDOM)


class EmailNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    sent_from = serializers.EmailField(max_length=254)

    class Meta(_NotiTemplateAdminSerializerBase.Meta):
        model = EmailNotificationTemplate


class NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    class Meta(_NotiTemplateAdminSerializerBase.Meta):
        model = NHNCloudKakaoAlimTalkNotificationTemplate
        read_only_fields = (
            _NotiTemplateAdminSerializerBase.Meta.fields
        )  # NHN Cloud Console에서 관리되므로 모든 필드 read-only.


class NHNCloudSMSNotificationTemplateAdminSerializer(_NotiTemplateAdminSerializerBase):
    sent_from = serializers.CharField(max_length=13)

    class Meta(_NotiTemplateAdminSerializerBase.Meta):
        model = NHNCloudSMSNotificationTemplate


class NotificationTemplateRenderRequestAdminSerializer(serializers.Serializer):
    context = serializers.JSONField(required=False, default=dict)


# ---- Query params -----------------------------------------------------------


class NotificationHistoryRetryRequestAdminSerializer(serializers.Serializer):
    status = serializers.ListField(
        child=serializers.ChoiceField(choices=NotificationStatus.choices),
        required=False,
        default=[NotificationStatus.FAILED],
    )
