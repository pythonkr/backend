import re

from cms.models import Page, Section, Sitemap
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from rest_framework import serializers


class SitemapAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = COMMON_ADMIN_FIELDS + (
            "parent_sitemap",
            "route_code",
            "order",
            "page",
            "external_link",
            "name_ko",
            "name_en",
            "hide",
        )

    def validate_route_code(self, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]*$", value):
            raise serializers.ValidationError("route_code는 알파벳, 숫자, 언더바(_)로만 구성되어야 합니다.")

        return value

    def validate_external_link(self, value: str | None) -> str | None:
        # 빈 string인 경우 None으로 처리
        return value or None

    def validate_parent_sitemap(self, value: Sitemap | None) -> Sitemap | None:
        if not value:
            return None

        if parent_sitemap := self.instance:
            while parent_sitemap:
                if value == parent_sitemap:
                    raise serializers.ValidationError("Parent Sitemap이 본인 또는 자식 Sitemap을 가리킬 수 없습니다.")
                parent_sitemap = parent_sitemap.parent_sitemap

        return value

    def validate(self, attrs: dict) -> dict:
        page = attrs.get("page", getattr(self.instance, "page", None))
        external_link = attrs.get("external_link", getattr(self.instance, "external_link", None))

        if not (page or external_link):
            raise serializers.ValidationError("Page 또는 External Link 중 하나는 반드시 선택 또는 입력해야 합니다.")
        if page and external_link:
            raise serializers.ValidationError("Page, External Link 중 하나만 선택 또는 입력할 수 있습니다.")

        return attrs


class PageAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = COMMON_ADMIN_FIELDS + ("title_ko", "title_en", "show_top_title_banner", "show_bottom_sponsor_banner")


class SectionAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    page = serializers.PrimaryKeyRelatedField(queryset=Page.objects.filter_active(), required=False)

    class Meta:
        model = Section
        fields = COMMON_ADMIN_FIELDS + ("page", "external_link", "order", "body_ko", "body_en")
