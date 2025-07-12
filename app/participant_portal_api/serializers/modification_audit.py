import types
import typing
import unicodedata
import uuid

from core.util.django_orm import get_diff_data_from_jsonized_models, model_to_jsonable_dict
from core.util.thread_local import get_current_user
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from rest_framework import serializers
from user.models import UserExt


class ModificationAuditResponsePortalSerializer(serializers.ModelSerializer):
    class ModificationAuditCommentPortalSerializer(serializers.ModelSerializer):
        class ModificationAuditCommentPortalUserSerializer(serializers.ModelSerializer):
            class Meta:
                model = UserExt
                fields = read_only_fields = ("id", "nickname", "is_superuser")

        created_by = ModificationAuditCommentPortalUserSerializer(read_only=True)

        class Meta:
            model = ModificationAuditComment
            fields = read_only_fields = ("id", "content", "created_at", "created_by", "updated_at")

    instance_type = serializers.CharField(source="instance_type.model", read_only=True)
    comments = ModificationAuditCommentPortalSerializer(many=True, read_only=True)
    str_repr = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = ModificationAudit
        fields = read_only_fields = (
            "id",
            "status",
            "created_at",
            "updated_at",
            "instance_type",
            "instance_id",
            "modification_data",
            "comments",
            "str_repr",
        )


class ModificationAuditCreationPortalSerializer(serializers.ModelSerializer):
    has_requested_modification_audit = serializers.SerializerMethodField()
    requested_modification_audit_id = serializers.SerializerMethodField()

    @staticmethod
    def get_requested_modification_audit(instance: models.Model) -> ModificationAudit | None:
        return ModificationAudit.objects.filter_requested(instance).first()

    def get_has_requested_modification_audit(self, obj: models.Model) -> bool:
        return True if self.get_requested_modification_audit(obj) else False

    def get_requested_modification_audit_id(self, obj: models.Model) -> uuid.UUID | None:
        if (mod_audit := self.get_requested_modification_audit(obj)) and mod_audit.created_by == get_current_user():
            return mod_audit.id

        return None

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)

        if not self.instance:
            # 정상 요청인 경우 이 로직을 타면 안되므로, 500 Server Error가 발생하도록 ValueError를 일으킵니다.
            raise ValueError("Target instance is required for modification request.")

        if not isinstance(self.instance, ModificationAudit.REGISTERED_INSTANCE_TYPES):
            # 정상 요청인 경우 이 로직을 타면 안되므로, 500 Server Error가 발생하도록 ValueError를 일으킵니다.
            raise ValueError("Modification requests can only be made for registered instance types.")

        if ModificationAudit.objects.filter_requested(self.instance).exists():
            raise serializers.ValidationError(
                "이미 심사 중인 수정 요청이 있습니다. 수정 요청을 철회한 후 다시 시도해주세요.\n"
                "There is already a modification request that currently under review.\n"
                "Please cancel the existing request and try again."
            )

        return attrs

    def save(self, **kwargs: dict) -> types.SimpleNamespace:
        """instance.save()를 호출하는 대신, 변경된 데이터를 추출하여 ModificationAudit 인스턴스를 생성합니다."""
        instance_type = ContentType.objects.get_for_model(self.instance)
        instance_key = str(self.instance.pk)
        original_data = model_to_jsonable_dict(self.instance)["model_data"]

        with transaction.atomic(savepoint=True):
            updated_instance = self.update(self.instance, self.validated_data)
            updated_instance.refresh_from_db()
            updated_data = model_to_jsonable_dict(updated_instance)["model_data"]
            transaction.set_rollback(True)

        if not (diff_data := get_diff_data_from_jsonized_models(original_data, updated_data)):
            raise serializers.ValidationError("변경된 데이터가 없습니다.\nNo modification data provided.")

        audit: ModificationAudit = ModificationAudit.objects.create(
            instance_type=instance_type,
            instance_id=instance_key,
            original_data=original_data,
            modification_data=diff_data,
        )
        audit.notify_creation_to_slack()
        return audit.fake_modified_instance


class ModificationAuditCancelPortalSerializer(serializers.ModelSerializer):
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
            raise serializers.ValidationError(
                "심사가 진행 중인 수정 요청만 철회할 수 있습니다.\n"
                "You can only cancel a modification request that is currently under review."
            )

        return attrs

    def save(self, **kwargs: dict) -> ModificationAudit:
        super().save(**kwargs)
        instance: ModificationAudit = self.instance
        instance.status = ModificationAudit.Status.CANCELLED
        instance.save(update_fields=["status"])

        if reason := self.validated_data["reason"]:
            ModificationAuditComment.objects.create(audit=instance, content=reason)

        return instance
