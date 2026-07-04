from __future__ import annotations

from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.pk_related_serializer_field import PrimaryKeyRelatedSerializerField
from django.db.transaction import atomic
from rest_framework import serializers
from user.models import UserExt
from user.models.merge import MergeError, UserMergeHistory, UserMergeObject


class UserMergeHistoryListAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class UserExtSerializer(serializers.ModelSerializer):
        str_repr = serializers.CharField(source="__str__", read_only=True)

        class Meta:
            model = UserExt
            fields = ("id", "username", "email", "nickname", "is_active", "str_repr")

    source = PrimaryKeyRelatedSerializerField(queryset=UserExt.objects.all(), serializer=UserExtSerializer)
    target = PrimaryKeyRelatedSerializerField(queryset=UserExt.objects.all(), serializer=UserExtSerializer)
    is_self_merge = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserMergeHistory
        fields = COMMON_ADMIN_FIELDS + ("source", "target", "is_self_merge", "reverted_at")

    def validate(self, attrs: dict) -> dict:
        if attrs["source"] == attrs["target"]:
            raise serializers.ValidationError({"target": MergeError("same_account").localized(en=False)})
        return attrs

    def create(self, validated_data: dict) -> UserMergeHistory:
        try:
            with atomic():
                history = super().create(validated_data)
                history.merge()
        except MergeError as e:
            raise serializers.ValidationError({"detail": e.localized(en=False)}) from e
        return history


class UserMergeHistoryAdminSerializer(UserMergeHistoryListAdminSerializer):
    class UserMergeObjectAdminSerializer(serializers.ModelSerializer):
        target_type_app = serializers.CharField(read_only=True)
        target_type_resource = serializers.CharField(read_only=True)

        class Meta:
            model = UserMergeObject
            fields = ("id", "target_type_app", "target_type_resource", "target_id", "field_names")

    merged_objects = UserMergeObjectAdminSerializer(many=True, read_only=True)

    class Meta(UserMergeHistoryListAdminSerializer.Meta):
        fields = UserMergeHistoryListAdminSerializer.Meta.fields + ("merged_objects",)
