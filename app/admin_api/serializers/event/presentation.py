from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType
from file.models import PublicFile
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
    class PresentationCategoryField(serializers.PrimaryKeyRelatedField):
        def get_queryset(self):
            qs = super().get_queryset()
            return qs.filter(type=self.instance.type) if self.instance else qs.none()

    categories = PresentationCategoryField(
        many=True, required=False, queryset=PresentationCategory.objects.filter_active()
    )

    class Meta:
        model = Presentation
        fields = COMMON_ADMIN_FIELDS + (
            "categories",
            "type",
            "title_ko",
            "title_en",
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
