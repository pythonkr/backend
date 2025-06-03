from rest_framework import serializers


class BaseAbstractSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_by = serializers.StringRelatedField()
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    updated_by = serializers.StringRelatedField()
    deleted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    deleted_by = serializers.StringRelatedField()

    str_repr = serializers.CharField(source="__str__", read_only=True)
