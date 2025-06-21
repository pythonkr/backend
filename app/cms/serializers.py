from cms.models import Page, Section, Sitemap
from core.const.serializer import COMMON_FIELDS
from rest_framework import serializers


class SitemapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = COMMON_FIELDS + (
            "parent_sitemap",
            "route_code",
            "name",
            "order",
            "page",
            "external_link",
            "hide",
        )


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = COMMON_FIELDS + ("order", "css", "body")


class PageSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True, source="active_sections")

    class Meta:
        model = Page
        fields = COMMON_FIELDS + (
            "title",
            "subtitle",
            "css",
            "sections",
            "show_top_title_banner",
            "show_bottom_sponsor_banner",
        )
