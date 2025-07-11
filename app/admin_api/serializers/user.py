import functools
import typing

from admin_api.serializers.modification_audit import ModificationAuditResponseAdminSerializer
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from django.core.files.storage import storages
from participant_portal_api.models import ModificationAudit
from rest_framework import serializers
from user.models import UserExt
from user.models.organization import Organization


class UserAdminSerializer(JsonSchemaSerializer, serializers.ModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = UserExt
        fields = (
            "id",
            "is_active",
            "username",
            "email",
            "image",
            "nickname_ko",
            "nickname_en",
            "is_superuser",
            "str_repr",
            "date_joined",
            "last_login",
        )
        extra_kwargs = {
            "id": {"read_only": True},
            "date_joined": {"read_only": True},
            "last_login": {"read_only": True},
        }


class UserModificationAuditPreviewAdminSerializer(serializers.ModelSerializer):
    class UserSerializer(serializers.ModelSerializer):
        image = serializers.SerializerMethodField()

        class Meta:
            model = UserExt
            fields = ("id", "image", "email", "nickname_ko", "nickname_en")

        def get_image(self, obj: UserExt) -> str | None:
            return storages["public"].url(str(obj.image.file)) if obj.image else None

    modification_audit = ModificationAuditResponseAdminSerializer(source="*")
    original = UserSerializer(source="fake_original_instance")
    modified = UserSerializer(source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = ("modification_audit", "original", "modified")


class UserAdminSignInSerializerData(typing.TypedDict):
    identity: str
    password: str


class UserAdminSignInSerializer(JsonSchemaSerializer, ReadOnlyModelSerializer):
    identity = serializers.CharField(max_length=150, required=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        fields = ("identity", "password")

    @functools.cached_property
    def user(self) -> UserExt | None:
        identity = typing.cast(UserAdminSignInSerializerData, self.initial_data)["identity"].strip()
        field = "username" if identity.startswith("@") or "@" not in identity else "email"
        return UserExt.objects.filter(**{field: identity, "is_active": True}).first()

    def validate(self, attrs: UserAdminSignInSerializerData) -> UserAdminSignInSerializerData:
        if not (self.user and self.user.check_password(attrs["password"])):
            raise serializers.ValidationError("User not found or inactive or wrong password.")

        if not self.user.is_superuser:
            raise serializers.PermissionDenied("Only permissioned users can sign in using this route.")

        return attrs


class UserAdminPasswordChangeSerializerData(typing.TypedDict):
    old_password: str
    new_password: str
    new_password_confirm: str


class UserAdminPasswordChangeSerializer(JsonSchemaSerializer, ReadOnlyModelSerializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = UserExt
        fields = ("old_password", "new_password", "new_password_confirm")

    def validate(self, attrs: UserAdminPasswordChangeSerializerData) -> UserAdminPasswordChangeSerializerData:
        user: UserExt = self.instance
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError("Old password is incorrect.")

        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError("New password cannot be the same as the old password.")

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError("New password and confirmation do not match.")

        return attrs

    def save(self, **kwargs: typing.Any) -> UserExt:
        user: UserExt = self.instance
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class OrganizationAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = COMMON_ADMIN_FIELDS + ("name_ko", "name_en")
