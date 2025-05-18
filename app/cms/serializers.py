from cms.models import Page, Section, Sitemap
from rest_framework import serializers


class SitemapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = ("id", "parent_sitemap", "name", "order", "page")


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ("id", "order", "css", "body")


class PageSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Page
        fields = ("id", "title", "subtitle", "css", "sections", "created_at", "updated_at")
