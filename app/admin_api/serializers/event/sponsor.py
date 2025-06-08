from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.sponsor.models import Sponsor, SponsorTier
from rest_framework import serializers


class SponsorTierAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = SponsorTier
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en", "order")


class SponsorAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = COMMON_ADMIN_FIELDS + ("event", "logo", "page", "name_ko", "name_en")
