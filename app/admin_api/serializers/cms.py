import re

from cms.models import DomainGroup, Page, Section, Sitemap
from core.const.regex import HOSTNAME_REGEX
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.db import IntegrityError, transaction
from rest_framework import serializers


class DomainGroupAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    # DRF가 ArrayField를 자동 매핑하면 inner CharField의 validator를 raw input(정규화 전)에 적용해 정상 입력도 거부됨.
    # 이를 막기 위해 inner validator 없는 ListField로 재정의하고, 정규화 + format 검증 + 그룹 간 중복 검증을 validate_domains에서 명시적으로 수행.
    domains = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    class Meta:
        model = DomainGroup
        fields = COMMON_ADMIN_FIELDS + ("name", "domains")

    def validate_domains(self, value: list[str]) -> list[str]:
        if not (normalized := list({c for v in value if (c := v.strip().lower())})):
            raise serializers.ValidationError("도메인 목록이 비어있을 수 없습니다.")

        if invalid := [d for d in normalized if not HOSTNAME_REGEX.match(d)]:
            raise serializers.ValidationError(
                [
                    f"`{d}` 도메인이 올바른 호스트 형식이 아닙니다 (스킴/포트/경로/쿼리는 포함할 수 없습니다)."
                    for d in invalid
                ]
            )

        overlap_qs = DomainGroup.objects.filter_active().filter(domains__overlap=normalized)
        if self.instance and self.instance.pk:
            overlap_qs = overlap_qs.exclude(pk=self.instance.pk)

        if conflict := overlap_qs.first():
            shared = sorted(set(normalized) & set(conflict.domains))
            err_msg = f"`{', '.join(shared)}` 도메인이 이미 `{conflict.name}` 그룹에 등록되어 있습니다."
            raise serializers.ValidationError(err_msg)

        return normalized

    @transaction.atomic
    def save(self, **kwargs):
        try:
            instance = super().save(**kwargs)
        except IntegrityError as e:
            # DB-level overlap trigger가 race condition을 잡아낸 경우 (app-level 검사가 통과한 동시 요청).
            if "cms_domaingroup_domains_no_overlap" in str(e):
                raise serializers.ValidationError({"domains": "도메인이 이미 다른 그룹에 등록되어 있습니다."}) from e
            raise

        if not instance.sitemaps.filter_active().exists():
            page = Page.objects.create(title=instance.name, subtitle=instance.name)
            Section.objects.create(page=page, order=0, body="")
            Sitemap.objects.create(domain_group=instance, name=instance.name, route_code="", page=page)
        return instance


class SitemapAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Sitemap
        fields = COMMON_ADMIN_FIELDS + (
            "domain_group",
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

        # 순환 참조를 방지하기 위한 검증
        parent_sitemap = value
        while parent_sitemap:
            if parent_sitemap == self.instance:
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

        merged = {**attrs}
        if self.instance is not None:
            for field in ("domain_group", "parent_sitemap", "route_code"):
                merged.setdefault(field, getattr(self.instance, field, None))

        duplicates = Sitemap.objects.filter_active().filter(
            domain_group=merged.get("domain_group"),
            parent_sitemap=merged.get("parent_sitemap"),
            route_code=merged.get("route_code") or "",
        )
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            msg = "동일한 도메인 그룹과 상위 항목 내에 같은 route_code가 이미 존재합니다."
            raise serializers.ValidationError({"route_code": msg})

        return attrs


class PageAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = COMMON_ADMIN_FIELDS + (
            "title_ko",
            "title_en",
            "css",
            "show_top_title_banner",
            "show_bottom_sponsor_banner",
        )


class SectionAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    page = serializers.PrimaryKeyRelatedField(queryset=Page.objects.filter_active(), required=False)

    class Meta:
        model = Section
        fields = COMMON_ADMIN_FIELDS + ("page", "order", "css", "body_ko", "body_en")
