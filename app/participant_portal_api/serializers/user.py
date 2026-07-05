import typing
import unicodedata

from core.util.thread_local import get_current_user
from file.models import PublicFile
from participant_portal_api.serializers.modification_audit import ModificationAuditCreationPortalSerializer
from rest_framework import serializers
from user.models import UserExt


def normalize_str(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip() if value else ""


class UserPortalSerializer(ModificationAuditCreationPortalSerializer, serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nickname = serializers.CharField(read_only=True)  # django-modeltranslation에 의해 accept-language에 따라 응답됨
    profile_image = serializers.FileField(read_only=True, allow_null=True, source="image.file")

    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)

    class Meta:
        model = UserExt
        fields = (
            "id",
            "email",
            "profile_image",
            "username",
            "nickname",
            "nickname_ko",
            "nickname_en",
            "image",
            "has_requested_modification_audit",
            "requested_modification_audit_id",
        )

    def validate_image(self, image: PublicFile | None) -> PublicFile | None:
        if not image:
            return None

        image_owner = image.created_by or image.updated_by
        if (current_user := get_current_user()) and not (image_owner == current_user == self.instance):
            raise serializers.ValidationError("You can only set your own profile image.")

        return image

    def validate(self, attrs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        if self.instance != get_current_user():
            raise serializers.ValidationError("You can only update your own profile.")

        return super().validate(attrs)
