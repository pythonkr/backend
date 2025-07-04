import functools
import typing
import unicodedata

from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from core.util.thread_local import get_current_user
from file.models import PublicFile
from rest_framework import serializers
from user.models import UserExt


def normalize_str(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip() if value else ""


class UserPortalSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nickname = serializers.CharField(read_only=True)  # django-modeltranslation에 의해 accept-language에 따라 응답됨
    profile_image = serializers.FileField(read_only=True, allow_null=True, source="image.file")

    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)

    class Meta:
        model = UserExt
        fields = ("id", "email", "profile_image", "username", "nickname", "nickname_ko", "nickname_en", "image")

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


class UserPortalSignInSerializer(ReadOnlyModelSerializer):
    identity = serializers.CharField(max_length=150, required=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        fields = ("identity", "password")

    @functools.cached_property
    def user(self) -> UserExt | None:
        if not (email := normalize_str(self.initial_data.get("identity", ""))):
            return None

        return UserExt.objects.filter(is_active=True, email=email).first()

    def validate_identity(self, email: str) -> str:
        if not (email := normalize_str(email)):
            raise serializers.ValidationError("Email cannot be empty.")

        if not self.user:
            raise serializers.ValidationError("User not found or inactive or wrong password.")

        return email

    def validate_password(self, password: str) -> str:
        if not (password := normalize_str(password)):
            raise serializers.ValidationError("Password cannot be empty.")

        return password

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        if not (self.user and self.user.check_password(attrs["password"])):
            raise serializers.ValidationError("User not found or inactive or wrong password.")

        return attrs


class UserPortalPasswordChangeSerializer(ReadOnlyModelSerializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = UserExt
        fields = ("old_password", "new_password", "new_password_confirm")

    def validate_old_password(self, old_password: str) -> str:
        if not (old_password := normalize_str(old_password)):
            raise serializers.ValidationError("Old password cannot be empty.")
        return old_password

    def validate_new_password(self, new_password: str) -> str:
        if not (new_password := normalize_str(new_password)):
            raise serializers.ValidationError("New password cannot be empty.")
        return new_password

    def validate_new_password_confirm(self, new_password_confirm: str) -> str:
        if not (new_password_confirm := normalize_str(new_password_confirm)):
            raise serializers.ValidationError("New password confirmation cannot be empty.")
        return new_password_confirm

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        user: UserExt = self.instance
        old_password, new_password, new_password_confirm = (
            attrs["old_password"],
            attrs["new_password"],
            attrs["new_password_confirm"],
        )

        if not user.check_password(old_password):
            raise serializers.ValidationError("Old password is incorrect.")

        if new_password == old_password:
            raise serializers.ValidationError("New password cannot be the same as the old password.")

        if new_password != new_password_confirm:
            raise serializers.ValidationError("New password and confirmation do not match.")

        return attrs

    def save(self, **kwargs: typing.Any) -> UserExt:
        user: UserExt = self.instance
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
