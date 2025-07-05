import typing
import unicodedata

from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from rest_framework import serializers
from user.models import UserExt


class ModificationAuditResponseAdminSerializer(serializers.ModelSerializer):
    class ModificationAuditCommentAdminSerializer(serializers.ModelSerializer):
        class ModificationAuditCommentAdminUserSerializer(serializers.ModelSerializer):
            class Meta:
                model = UserExt
                fields = read_only_fields = ("id", "nickname", "is_superuser")

        created_by = ModificationAuditCommentAdminUserSerializer(read_only=True)

        class Meta:
            model = ModificationAuditComment
            fields = read_only_fields = ("id", "content", "created_at", "created_by", "updated_at")

    class ModificationAuditResponseInstanceAdminSerializer(serializers.Serializer):
        model = serializers.CharField(source="instance_type.model")
        app = serializers.CharField(source="instance_type.app_label")
        id = serializers.CharField(source="instance_id")

    comments = ModificationAuditCommentAdminSerializer(many=True, read_only=True)
    str_repr = serializers.CharField(source="__str__", read_only=True)
    instance = ModificationAuditResponseInstanceAdminSerializer(source="*", read_only=True)

    class Meta:
        model = ModificationAudit
        fields = read_only_fields = (
            "id",
            "status",
            "created_at",
            "updated_at",
            "instance",
            "modification_data",
            "comments",
            "str_repr",
        )


class ModificationAuditApprovalAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModificationAudit
        fields = read_only_fields = ("id",)

    def validate(self, attrs: dict) -> dict:
        if typing.cast(ModificationAudit, self.instance).status != ModificationAudit.Status.REQUESTED:
            raise serializers.ValidationError("심사가 진행 중인 수정 요청만 승인할 수 있습니다.")

        return attrs

    def save(self, **kwargs: dict) -> ModificationAudit:
        instance: ModificationAudit = self.instance
        instance.status = ModificationAudit.Status.APPROVED
        instance.apply_modification()
        instance.save()

        return instance


class ModificationAuditRejectionAdminSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(required=True, allow_blank=True, allow_null=True, write_only=True)

    class Meta:
        model = ModificationAudit
        fields = ("reason",)

    def validate_reason(self, reason: str | None) -> str | None:
        if not (reason and (normalized_reason := unicodedata.normalize("NFC", reason).strip())):
            return None

        return normalized_reason

    def validate(self, attrs: dict) -> dict:
        if typing.cast(ModificationAudit, self.instance).status != ModificationAudit.Status.REQUESTED:
            raise serializers.ValidationError("심사가 진행 중인 수정 요청만 반려할 수 있습니다.")

        return attrs

    def save(self, **kwargs: dict) -> ModificationAudit:
        instance: ModificationAudit = self.instance
        instance.status = ModificationAudit.Status.REJECTED
        instance.save(update_fields=["status"])

        if reason := self.validated_data["reason"]:
            ModificationAuditComment.objects.create(audit=instance, content=reason)

        return instance
