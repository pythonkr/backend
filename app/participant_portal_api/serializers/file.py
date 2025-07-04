from file.models import PublicFile
from rest_framework import serializers


class PublicFilePortalSerializer(serializers.ModelSerializer):
    file = serializers.FileField(read_only=True)
    name = serializers.CharField(read_only=True, source="file.name")

    class Meta:
        model = PublicFile
        fields = ("id", "file", "name", "created_at")


class PublicFilePortalUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def create(self, validated_data: dict) -> PublicFile:
        new_file = PublicFile(file=validated_data["file"])
        new_file.clean()

        if new_file.hash and (pf := PublicFile.objects.filter(hash=new_file.hash).first()):
            return pf

        new_file.save()
        return new_file
