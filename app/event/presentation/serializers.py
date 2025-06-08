from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker
from rest_framework import serializers


class PresentationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = ("id", "name")


class PresentationSpeakerSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(source="user.nickname", read_only=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "nickname", "biography")


class PresentationSerializer(serializers.ModelSerializer):
    categories = PresentationCategorySerializer(source="active_categories", many=True, read_only=True)
    speakers = PresentationSpeakerSerializer(source="active_speakers", many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = ("id", "title", "categories", "speakers")
