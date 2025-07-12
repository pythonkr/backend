import typing
import unicodedata

from event.presentation.models import Presentation, PresentationSpeaker
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
        app = serializers.SerializerMethodField(read_only=True)
        id = serializers.CharField(source="instance_id")

        class Meta:
            fields = read_only_fields = ("model", "app", "id")

        def get_app(self, obj: ModificationAudit) -> str:
            return type(obj.instance).__module__.split(".")[0]

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
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)

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

        if reason := self.validated_data.get("reason"):
            ModificationAuditComment.objects.create(audit=instance, content=reason)

        instance.status = ModificationAudit.Status.REJECTED
        instance.save(update_fields=["status"])
        return instance


class PresentationModificationAuditPreviewAdminSerializer(serializers.ModelSerializer):
    class PresentationSerializer(serializers.ModelSerializer):
        class PresentationSpeakerSerializer(serializers.ModelSerializer):
            class UserSerializer(serializers.ModelSerializer):
                class Meta:
                    model = UserExt
                    fields = ("id", "nickname_ko", "nickname_en")

            user = UserSerializer()
            image_id = serializers.CharField(source="image.id", allow_null=True, required=False)

            class Meta:
                model = PresentationSpeaker
                fields = ("id", "user", "image_id", "biography_ko", "biography_en")

        type = serializers.CharField(source="type.name_ko")
        categories = serializers.SerializerMethodField()
        image_id = serializers.CharField(source="image.id", allow_null=True, required=False)
        speakers = PresentationSpeakerSerializer(many=True)

        class Meta:
            model = Presentation
            fields = (
                "type",
                "categories",
                "image_id",
                "title_ko",
                "title_en",
                "summary_ko",
                "summary_en",
                "description_ko",
                "description_en",
                "speakers",
            )

        def get_categories(self, obj: Presentation) -> list[str]:
            return [cat.name_ko for cat in obj.categories]

    modification_audit = ModificationAuditResponseAdminSerializer(source="*")
    original = PresentationSerializer(source="fake_original_instance")
    modified = PresentationSerializer(source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = ("modification_audit", "original", "modified")


class UserModificationAuditPreviewAdminSerializer(serializers.ModelSerializer):
    class UserSerializer(serializers.ModelSerializer):
        image_id = serializers.CharField(source="image.id", allow_null=True, required=False)

        class Meta:
            model = UserExt
            fields = ("id", "image_id", "email", "nickname_ko", "nickname_en")

    modification_audit = ModificationAuditResponseAdminSerializer(source="*")
    original = UserSerializer(source="fake_original_instance")
    modified = UserSerializer(source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = ("modification_audit", "original", "modified")
