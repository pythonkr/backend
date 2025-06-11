from cms.models import Page, Section, Sitemap
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from rest_framework import serializers


class SitemapAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = COMMON_ADMIN_FIELDS + ("parent_sitemap", "route_code", "order", "page", "name_ko", "name_en", "hide")


class PageAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = COMMON_ADMIN_FIELDS + (
            "title_ko",
            "title_en",
            "subtitle_ko",
            "subtitle_en",
            "show_top_title_banner",
            "show_bottom_sponsor_banner",
        )


class SectionAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    page = serializers.PrimaryKeyRelatedField(queryset=Page.objects.filter_active(), required=False)

    class Meta:
        model = Section
        fields = COMMON_ADMIN_FIELDS + ("page", "order", "body_ko", "body_en")
