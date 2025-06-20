from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
from rest_framework import serializers


class SponsorTierAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = SponsorTier
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en", "order")


class SponsorTagAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = SponsorTag
        fields = COMMON_ADMIN_FIELDS + ("event", "name_ko", "name_en")


class SponsorAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    tiers = serializers.PrimaryKeyRelatedField(many=True, queryset=SponsorTier.objects.filter_active())
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=SponsorTag.objects.filter_active())

    class Meta:
        model = Sponsor
        fields = COMMON_ADMIN_FIELDS + ("event", "logo", "sitemap", "name_ko", "name_en", "tiers", "tags")
