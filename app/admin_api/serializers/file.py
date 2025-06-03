from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from file.models import PublicFile
from rest_framework import serializers


class PublicFileAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    file = serializers.FileField(read_only=True)
    mimetype = serializers.CharField(read_only=True, allow_blank=True, allow_null=True, required=False)
    hash = serializers.CharField(read_only=True, allow_blank=True, allow_null=True, required=False)
    size = serializers.IntegerField(read_only=True, allow_null=True, required=False)

    class Meta:
        model = PublicFile
        fields = COMMON_ADMIN_FIELDS + ("file", "mimetype", "hash", "size")


class PublicFileAdmimUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def create(self, validated_data: dict) -> PublicFile:
        new_file = PublicFile(file=validated_data["file"])
        new_file.clean()

        if new_file.hash and (existing_file := PublicFile.objects.filter(hash=new_file.hash).first()):
            return existing_file

        new_file.save()

        return new_file
