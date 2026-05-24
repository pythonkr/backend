from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.lowercased_email_field import LowercasedEmailField
from core.serializer.nested_model_serializer import NestedModelSerializer
from rest_framework import serializers


class SocialAppAdminSerializer(JsonSchemaSerializer, serializers.ModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = SocialApp
        fields = ("id", "provider", "provider_id", "name", "client_id", "secret", "key", "settings", "str_repr")
        read_only_fields = ("id",)


class SocialAccountAdminSerializer(JsonSchemaSerializer, serializers.ModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = SocialAccount
        read_only_fields = fields = (
            "id",
            "user",
            "provider",
            "uid",
            "last_login",
            "date_joined",
            "extra_data",
            "str_repr",
        )


class EmailAddressAdminSerializer(JsonSchemaSerializer, serializers.ModelSerializer):
    str_repr = serializers.CharField(source="__str__", read_only=True)
    email = LowercasedEmailField()

    class Meta:
        model = EmailAddress
        fields = ("id", "user", "email", "verified", "primary", "str_repr")
        extra_kwargs = {"id": {"read_only": True}}


class EmailAddressNestedAdminSerializer(JsonSchemaSerializer, NestedModelSerializer):
    id = serializers.IntegerField(required=False, help_text="기존 EmailAddress 수정 시 PK 전달, 새로 추가 시 생략")
    email = LowercasedEmailField()

    class Meta:
        model = EmailAddress
        fields = ("id", "user", "email", "verified", "primary")
        # user 는 NestedFieldSpec.parent_fk_name 으로 부모 인스턴스에서 주입되므로 입력 시 생략 가능.
        extra_kwargs = {"user": {"required": False}}
        # validators=[] — auto UniqueTogetherValidator(user, email) 가 user 누락 시 required 로 막음.
        # DB unique constraint(account_emailaddress_user_id_email) 가 여전히 enforce.
        validators: list = []


class SocialAccountNestedAdminSerializer(JsonSchemaSerializer, NestedModelSerializer):
    # delete-only nested — id 로 기존 row 매칭만 함. UserAdminSerializer.validate_social_accounts 가 정책 강제.
    id = serializers.IntegerField(required=True)

    class Meta:
        model = SocialAccount
        read_only_fields = ("provider", "uid", "last_login", "date_joined", "extra_data")
        fields = ("id",) + read_only_fields
