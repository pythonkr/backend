import contextlib
import functools
import typing

from admin_api.serializers.socialaccount import EmailAddressNestedAdminSerializer, SocialAccountNestedAdminSerializer
from admin_api.services.socialaccount import delete_social_accounts_and_cleanup_user_emails
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from core.const.account import generate_random_password
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.external_apis.nhn_cloud.dooray import DoorayError, DoorayMember, nhn_cloud_dooray_client
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.nested_model_serializer import NestedFieldModelSerializer, NestedFieldSpec
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from core.util.thread_local import get_current_user
from rest_framework import serializers
from rest_framework.fields import empty
from user.models import UserExt
from user.models.organization import Organization

_DOORAY_KEY_MASK = "************"


class UserAdminSerializer(JsonSchemaSerializer, NestedFieldModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)
    email_addresses = EmailAddressNestedAdminSerializer(many=True, required=False, source="emailaddress_set")
    social_accounts = SocialAccountNestedAdminSerializer(many=True, required=False, source="socialaccount_set")

    dooray_api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dooray_account_info = serializers.SerializerMethodField(read_only=True)

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
            "email_addresses",
            "social_accounts",
            "dooray_api_key",
            "dooray_account_info",
        )
        extra_kwargs = {
            "id": {"read_only": True},
            "date_joined": {"read_only": True},
            "last_login": {"read_only": True},
        }
        nested_fields = {
            "emailaddress_set": NestedFieldSpec(
                related_manager_name="emailaddress_set",
                child_model=EmailAddress,
                parent_fk_name="user",
            ),
            "socialaccount_set": NestedFieldSpec(
                related_manager_name="socialaccount_set",
                child_model=SocialAccount,
                parent_fk_name="user",
            ),
        }

    def _dooray_me(self, token: str) -> DoorayMember | None:
        cache = self.__dict__.setdefault("_dooray_me_cache", {})
        if token not in cache:
            cache[token] = None
            with contextlib.suppress(DoorayError):
                cache[token] = nhn_cloud_dooray_client.members_me(token)
        return cache[token]

    def get_dooray_account_info(self, obj: UserExt) -> DoorayMember | None:
        if not obj.dooray_api_key or self.context.get("skip_dooray_connection_check"):
            return None
        return self._dooray_me(obj.dooray_api_key)

    def validate(self, attrs: dict) -> dict:
        # social_accounts=[] 는 마지막 SA cascade 를 트리거해 같은 user 의 EA 전체를 삭제함.
        # 같은 PATCH 의 email_addresses 입력은 cascade 로 즉시 사라져 의도와 다른 결과가 되므로,
        # 실제로 cascade 가 발생하는 경우(기존 SA 존재 + SA=[] + EA 입력 있음)에만 거부.
        if (
            attrs.get("socialaccount_set") == []
            and attrs.get("emailaddress_set")
            and self.instance is not None
            and self.instance.socialaccount_set.all()
        ):
            msg = "모든 SocialAccount 를 제거하면 EmailAddress 도 cascade 로 삭제됩니다 — 같은 PATCH 에서 EmailAddress 를 함께 변경할 수 없습니다."
            raise serializers.ValidationError(msg)
        return attrs

    def validate_social_accounts(self, value: list[dict]) -> list[dict]:
        # SocialAccount는 nested에서 delete-only — 모든 입력 id 가 이 유저의 기존 SA 와 매칭돼야 함.
        # PATCH(partial=True) 에서는 nested 의 required 가 풀려 id 가 없을 수 있음 — 명시적으로 거부.
        if any("id" not in item for item in value):
            raise serializers.ValidationError("SocialAccount는 nested API에서 생성할 수 없습니다 (id 필수).")
        provided_ids = {item["id"] for item in value}
        # UserAdminViewSet 의 prefetch_related 캐시 활용.
        existing_ids = {sa.id for sa in self.instance.socialaccount_set.all()} if self.instance else set()
        if unknown := provided_ids - existing_ids:
            msg = f"존재하지 않거나 이 유저의 것이 아닌 SocialAccount id: {sorted(map(str, unknown))}"
            raise serializers.ValidationError(msg)
        return value

    def validate_dooray_api_key(self, value: str | None) -> str | None:
        if not value or value == _DOORAY_KEY_MASK:
            return value
        if not self.instance:
            return None
        if not ((current := get_current_user()) and self.instance.pk == current.pk):
            raise serializers.ValidationError("본인 계정에만 Dooray 토큰을 등록할 수 있습니다.")
        if not (me := self._dooray_me(value)):
            raise serializers.ValidationError("유효하지 않거나 폐기된 Dooray 토큰입니다.")
        if (me.get("externalEmailAddress") or "").lower() not in self.instance.emails:
            raise serializers.ValidationError("Dooray 토큰의 이메일이 본인 계정 이메일과 일치하지 않습니다.")
        return value

    def create(self, validated_data: dict[str, typing.Any]) -> UserExt:
        password = generate_random_password()
        self._generated_password = password
        nested_data = {k: validated_data.pop(k, []) or [] for k in self.Meta.nested_fields}
        instance = UserExt.objects.create_user(**validated_data, password=password)
        self._apply_nested_sync(instance, nested_data)
        return instance

    def update(self, instance: UserExt, validated_data: dict[str, typing.Any]) -> UserExt:
        dooray_api_key = validated_data.pop("dooray_api_key", empty)
        if dooray_api_key not in {empty, _DOORAY_KEY_MASK}:
            instance.dooray_api_key = dooray_api_key or None

        return super().update(instance, validated_data)

    def to_representation(self, instance: UserExt) -> dict:
        data = super().to_representation(instance)
        if data["dooray_api_key"] and not self.context.get("show_dooray_api_key"):
            data["dooray_api_key"] = _DOORAY_KEY_MASK
        return data

    def _apply_nested_sync(self, instance: UserExt, nested_data: dict[str, list[dict] | None]) -> None:
        # SocialAccount는 delete-only — 기존 set 에서 input 에 없는 것만 삭제.
        sa_data = nested_data.pop("socialaccount_set", None)
        super()._apply_nested_sync(instance, nested_data)

        if sa_data is None:
            return

        provided_ids = {item["id"] for item in sa_data}
        # prefetch_related 캐시 활용.
        existing_ids = {sa.id for sa in instance.socialaccount_set.all()}
        if to_delete_ids := existing_ids - provided_ids:
            delete_social_accounts_and_cleanup_user_emails(SocialAccount.objects.filter(id__in=to_delete_ids))


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


class UserAdminPasswordResetResponseSerializer(serializers.Serializer):
    password = serializers.CharField(read_only=True)


class OrganizationAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = COMMON_ADMIN_FIELDS + ("name_ko", "name_en")
