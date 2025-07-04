from core.util.thread_local import get_current_user
from event.presentation.models import Presentation, PresentationSpeaker
from file.models import PublicFile
from rest_framework import serializers


class PresentationSpeakerPortalSerializer(serializers.ModelSerializer):
    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "biography_ko", "biography_en", "image", "user")


class PresentationPortalSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    summary = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)

    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)
    speakers = PresentationSpeakerPortalSerializer(many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = (
            "id",
            "title",
            "title_ko",
            "title_en",
            "summary",
            "summary_ko",
            "summary_en",
            "description",
            "description_ko",
            "description_en",
            "image",
            "speakers",
        )

    def to_representation(self, instance):
        result = super().to_representation(instance)

        if (current_user := get_current_user()) and (speakers := result.get("speakers")):
            result["speakers"] = [s for s in speakers if s["user"] == current_user.pk]

        return result
