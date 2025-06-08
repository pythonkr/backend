import functools
import typing

from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from rest_framework import serializers
from user.models import UserExt


class UserAdminSerializer(JsonSchemaSerializer, serializers.ModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = UserExt
        fields = (
            "id",
            "is_active",
            "username",
            "nickname_ko",
            "nickname_en",
            "email",
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
