from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType
from rest_framework import serializers


class PresentationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationType
        fields = ("id", "event", "name")


class PresentationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = ("id", "presentation_type", "name")


class PresentationSpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentationSpeaker
        fields = ("id", "presentation", "user", "name", "biography")


class PresentationSerializer(serializers.ModelSerializer):
    presentation_type = PresentationTypeSerializer(read_only=True)
    presentation_categories = PresentationCategorySerializer(many=True, read_only=True)
    presentation_speakers = PresentationSpeakerSerializer(many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = ("id", "presentation_type", "presentation_categories", "presentation_speakers")
