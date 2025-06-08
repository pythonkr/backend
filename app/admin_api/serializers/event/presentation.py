from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType
from rest_framework import serializers


class PresentationTypeAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationType
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en")


class PresentationCategoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationCategory
        fields = COMMON_ADMIN_FIELDS + ("type", "name_ko", "name_en")


class PresentationAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Presentation
        fields = COMMON_ADMIN_FIELDS + ("title_ko", "title_en")


class PresentationSpeakerAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = PresentationSpeaker
        fields = COMMON_ADMIN_FIELDS + ("presentation", "user", "biography_ko", "biography_en")
