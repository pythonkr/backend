import typing
import uuid

from core.util.thread_local import get_current_user
from event.presentation.models import Presentation, PresentationSpeaker
from file.models import PublicFile
from participant_portal_api.serializers.modification_audit import ModificationAuditCreationPortalSerializer
from rest_framework import serializers


class PresentationSpeakerPortalSerializer(serializers.ModelSerializer):
    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "biography_ko", "biography_en", "image", "user")


class PresentationSpeakerPortalData(typing.TypedDict):
    id: str | uuid.UUID
    biography_ko: str | None
    biography_en: str | None
    image: str | uuid.UUID | None


class PresentationPortalSerializer(ModificationAuditCreationPortalSerializer, serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    summary = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)

    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)
    speakers = PresentationSpeakerPortalSerializer(many=True, required=True)

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
            "has_requested_modification_audit",
            "requested_modification_audit_id",
        )

    def get_speaker_instance(self, speaker_id: str | uuid.UUID) -> PresentationSpeaker | None:
        return (
            PresentationSpeaker.objects.filter_active()
            .filter(
                presentation=self.instance,
                id=speaker_id,
                user=get_current_user(),
            )
            .first()
        )

    def to_representation(self, instance):
        result = super().to_representation(instance)

        if (current_user := get_current_user()) and (speakers := result.get("speakers")):
            result["speakers"] = [s for s in speakers if s["user"] == current_user.pk]

        return result

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)

        speakers = typing.cast(list[PresentationSpeakerPortalData], attrs["speakers"])
        if not isinstance(speakers, list):
            raise serializers.ValidationError("Speakers must be a list.")

        for speaker_data in speakers:
            if not (speaker_instance := self.get_speaker_instance(speaker_data["id"])):
                err_msg = f"Speaker with ID {speaker_data['id']} not found or does not belong to this presentation."
                raise serializers.ValidationError(err_msg)

            PresentationSpeakerPortalSerializer(
                instance=speaker_instance,
                data=speaker_data,
                partial=True,
            ).is_valid(raise_exception=True)

        return attrs
