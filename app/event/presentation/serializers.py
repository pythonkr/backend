from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker
from rest_framework import serializers


class PresentationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = ("id", "name")


class PresentationSpeakerSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "nickname", "biography", "image")


class PresentationSerializer(serializers.ModelSerializer):
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)
    categories = PresentationCategorySerializer(many=True, read_only=True)
    speakers = PresentationSpeakerSerializer(many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = ("id", "title", "description", "image", "categories", "speakers")
