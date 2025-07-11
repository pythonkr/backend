from admin_api.serializers.modification_audit import ModificationAuditResponseAdminSerializer
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.core.files.storage import storages
from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType
from file.models import PublicFile
from participant_portal_api.models import ModificationAudit
from rest_framework import serializers
from user.models import UserExt


class PresentationTypeAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationType
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en")


class PresentationCategoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = COMMON_ADMIN_FIELDS + ("type", "name_ko", "name_en")


class PresentationAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=PresentationCategory.objects.filter_active()
    )
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.filter_active(), allow_null=True, required=False
    )

    class Meta:
        model = Presentation
        fields = COMMON_ADMIN_FIELDS + (
            "type",
            "categories",
            "title_ko",
            "title_en",
            "summary_ko",
            "summary_en",
            "image",
            "description_ko",
            "description_en",
        )

    def validate(self, attrs: dict) -> dict:
        type = attrs.get("type", getattr(self.instance, "type", None))
        categories = attrs.get("categories", getattr(self.instance, "categories", []))

        if type and categories:
            if not all(category.type == type for category in categories):
                raise serializers.ValidationError("All categories must belong to the same type.")

        return super().validate(attrs)


class PresentationSpeakerAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=UserExt.objects.filter(is_active=True))
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.filter_active(), allow_null=True, required=False
    )

    class Meta:
        model = PresentationSpeaker
        fields = COMMON_ADMIN_FIELDS + ("presentation", "user", "image", "biography_ko", "biography_en")


class PresentationModificationAuditPreviewAdminSerializer(serializers.ModelSerializer):
    class PresentationSerializer(serializers.ModelSerializer):
        class PresentationSpeakerSerializer(serializers.ModelSerializer):
            class UserSerializer(serializers.ModelSerializer):
                class Meta:
                    model = UserExt
                    fields = ("id", "nickname_ko", "nickname_en")

            user = UserSerializer()
            image = serializers.SerializerMethodField()

            class Meta:
                model = PresentationSpeaker
                fields = ("id", "user", "image", "biography_ko", "biography_en")

            def get_image(self, obj: UserExt) -> str | None:
                return storages["public"].path(obj.image.file) if obj.image else None

        type = serializers.CharField(source="type.name_ko")
        categories = serializers.SerializerMethodField()
        speakers = PresentationSpeakerSerializer(many=True)

        class Meta:
            model = Presentation
            fields = (
                "type",
                "categories",
                "image",
                "title_ko",
                "title_en",
                "summary_ko",
                "summary_en",
                "description_ko",
                "description_en",
                "speakers",
            )

        def get_categories(self, obj: Presentation) -> list[str]:
            return [cat.name_ko for cat in obj.categories]

    modification_audit = ModificationAuditResponseAdminSerializer(source="*")
    original = PresentationSerializer(source="fake_original_instance")
    modified = PresentationSerializer(source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = ("modification_audit", "original", "modified")
