import typing
import uuid

from core.util.thread_local import get_current_user
from event.presentation.models import Presentation, PresentationSpeaker
from file.models import PublicFile
from participant_portal_api.serializers.modification_audit import ModificationAuditCreationPortalSerializer
from rest_framework import serializers
from user.models import UserExt


class PresentationUserPortalSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserExt
        fields = ("id", "email", "nickname_ko", "nickname_en")


class PresentationSpeakerPortalSerializer(serializers.ModelSerializer):
    image = serializers.PrimaryKeyRelatedField(queryset=PublicFile.objects.filter_active(), allow_null=True)
    user = PresentationUserPortalSerializer(read_only=True)

    class Meta:
        model = PresentationSpeaker
        fields = ("id", "biography_ko", "biography_en", "image", "user")

    def to_internal_value(self, data: dict) -> dict:
        """Override to_internal_value to ensure that the 'id' field is included in the validated data."""
        return super().to_internal_value(data) | {"id": data.get("id")}


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
            result["speakers"] = [s for s in speakers if s["user"]["id"] == current_user.pk]
        else:
            result["speakers"] = []

        return result

    def validate_speakers(self, value: list[PresentationSpeakerPortalData]) -> list[PresentationSpeakerPortalData]:
        if not isinstance(value, list):
            raise serializers.ValidationError("Speakers must be a list.")

        for speaker_data in value:
            if not isinstance(speaker_data, dict):
                raise serializers.ValidationError("Each speaker must be a dictionary.")

            if "id" not in speaker_data or not speaker_data["id"]:
                raise serializers.ValidationError("Each speaker must have a valid ID.")

            if not self.get_speaker_instance(speaker_data["id"]):
                err_msg = f"Speaker with ID {speaker_data['id']} not found or does not belong to this presentation."
                raise serializers.ValidationError(err_msg)

        return value

    def update(self, instance: Presentation, validated_data: dict) -> Presentation:
        speakers_data = validated_data.pop("speakers", [])
        instance = super().update(instance, validated_data)

        for speaker_data in speakers_data:
            if not (speaker_instance := self.get_speaker_instance(speaker_data["id"])):
                continue

            for attr, value in speaker_data.items():
                setattr(speaker_instance, attr, value)
            speaker_instance.save()

        return instance
