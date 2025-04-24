from cms.models import Page, Sitemap
from rest_framework import serializers


class SitemapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = "__all__"


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = "__all__"
