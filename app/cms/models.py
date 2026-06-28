from __future__ import annotations

import contextlib
import dataclasses
import datetime
import functools
import re
import typing
import uuid

from core.const.regex import HOSTNAME_PATTERN
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet, MarkdownField
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class DomainGroup(BaseAbstractModel):
    choices_meta_schema: typing.ClassVar[dict] = {
        "domains": {"label": "도메인", "type": "string", "filter": "search"},
    }

    name = models.CharField(max_length=128, help_text="예: '2025년 PyConKR 홈페이지'")
    domains = ArrayField(
        models.CharField(
            max_length=253,
            validators=[
                RegexValidator(
                    regex=HOSTNAME_PATTERN,
                    message="올바른 호스트 형식이 아닙니다 (스킴/포트/경로/쿼리는 포함할 수 없습니다).",
                )
            ],
        ),
        blank=False,
        help_text="이 그룹에 속한 frontend 도메인 호스트 목록 (스킴/포트/경로 제외).",
    )

    class Meta:
        indexes = [GinIndex(fields=["domains"])]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="uq__domain_group__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({', '.join(self.domains) or '없음'})"

    def _choice_meta_fields(self) -> dict:
        return {"domains": ", ".join(self.domains)}


class Page(BaseAbstractModel):
    choices_meta_schema: typing.ClassVar[dict] = {
        "subtitle": {"label": "부제목", "type": "string", "filter": "search"},
        "show_top_title_banner": {"label": "상단 타이틀 배너", "type": "boolean"},
        "show_bottom_sponsor_banner": {"label": "하단 스폰서 배너", "type": "boolean"},
    }

    css = models.TextField(null=True, blank=True, default=None)
    title = models.CharField(max_length=256)
    subtitle = models.CharField(max_length=512)

    show_top_title_banner = models.BooleanField(default=False, help_text="페이지 상단에 타이틀 배너를 표시할지 여부")
    show_bottom_sponsor_banner = models.BooleanField(
        default=False, help_text="페이지 하단에 스폰서 배너를 표시할지 여부"
    )

    def __str__(self):
        return str(self.title)

    def _choice_meta_fields(self) -> dict:
        return {
            "subtitle": self.subtitle,
            "show_top_title_banner": self.show_top_title_banner,
            "show_bottom_sponsor_banner": self.show_bottom_sponsor_banner,
        }

    def active_sections(self) -> list[Section]:
        with contextlib.suppress(AttributeError):
            return self._prefetched_active_sections

        return self.sections.filter_active().order_by("order")


@dataclasses.dataclass
class SitemapGraph:
    id: str
    parent_id: str | None
    route_code: str

    parent: SitemapGraph | None = None
    children: list[SitemapGraph] = dataclasses.field(default_factory=list)

    @functools.cached_property
    def route(self) -> str:
        if self.parent:
            return f"{self.parent.route}/{self.route_code}"
        return self.route_code


# route(=parent 체인 재귀)를 이 깊이까지 select_related로 미리 로드 (더 깊은 트리는 lazy fallback).
SITEMAP_ROUTE_PREFETCH_DEPTH = 6
SITEMAP_ROUTE_SELECT_RELATED = "__".join(["parent_sitemap"] * SITEMAP_ROUTE_PREFETCH_DEPTH)


class SitemapQuerySet(BaseAbstractModelQuerySet):
    def filter_by_today(self) -> typing.Self:
        now = datetime.datetime.now()
        return self.filter(
            models.Q(display_start_at__isnull=True) | models.Q(display_start_at__lte=now),
            models.Q(display_end_at__isnull=True) | models.Q(display_end_at__gte=now),
        )

    def filter_by_domain(self, domain: str | None) -> typing.Self:
        if not domain:
            return self.none()
        return self.filter(domain_group__domains__contains=[domain])

    def get_all_routes(self, domain_group_id: uuid.UUID) -> set[str]:
        flattened_graph: dict[str, SitemapGraph] = {
            id: SitemapGraph(id=id, parent_id=parent_id, route_code=route_code)
            for id, parent_id, route_code in self.filter(domain_group_id=domain_group_id).values_list(
                "id", "parent_sitemap_id", "route_code"
            )
        }
        roots: list[SitemapGraph] = []

        for node in flattened_graph.values():
            if node.parent_id is None:
                roots.append(node)
                continue

            parent_node = flattened_graph[node.parent_id]
            node.parent = parent_node
            parent_node.children.append(node)

        return {node.route for node in flattened_graph.values()}


class Sitemap(BaseAbstractModel):
    choices_select_related = (SITEMAP_ROUTE_SELECT_RELATED, "domain_group")
    choices_meta_schema: typing.ClassVar[dict] = {
        "domain_group": {"label": "도메인 그룹", "type": "string", "filter": "select"},
        "hide": {"label": "숨김", "type": "boolean"},
        "order": {"label": "순서", "type": "number"},
    }

    parent_sitemap = models.ForeignKey(
        "self", null=True, blank=True, default=None, on_delete=models.SET_NULL, related_name="children"
    )
    domain_group = models.ForeignKey(
        DomainGroup,
        on_delete=models.PROTECT,
        related_name="sitemaps",
        help_text="이 Sitemap이 노출될 frontend 도메인 그룹",
    )

    route_code = models.CharField(max_length=256, blank=True)
    name = models.CharField(max_length=256)
    order = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    page = models.ForeignKey(
        Page, on_delete=models.PROTECT, null=True, blank=True, help_text="Sitemap 클릭 시 보여질 Page"
    )
    external_link = models.URLField(
        null=True, blank=True, help_text="외부 링크인 경우 Page를 지정하는 대신 URL을 입력하세요."
    )

    hide = models.BooleanField(default=False, help_text="이 Sitemap을 숨길지 여부")

    display_start_at = models.DateTimeField(null=True, blank=True)
    display_end_at = models.DateTimeField(null=True, blank=True)

    objects: SitemapQuerySet = SitemapQuerySet.as_manager()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["domain_group", "parent_sitemap", "route_code"],
                name="uq__sitemap__domain_parent_route_code",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.route} ({self.name})"

    def _choice_meta_fields(self) -> dict:
        return {
            "domain_group": str(self.domain_group),
            "hide": self.hide,
            "order": self.order,
        }

    @functools.cached_property
    def route(self) -> str:
        """주의: 이 속성은 N+1 쿼리를 발생시킵니다. 절때 API 응답에서 사용하지 마세요."""
        if self.parent_sitemap:
            return f"{self.parent_sitemap.route}/{self.route_code}"
        return self.route_code

    def clean(self) -> None:
        # route_code는 URL-Safe하도록 알파벳, 숫자, 언더바(_)로만 구성되어야 함
        if not re.match(r"^[a-zA-Z0-9_-]*$", self.route_code):
            raise ValidationError("route_code는 알파벳, 숫자, 언더바(_)로만 구성되어야 합니다.")

        # Parent Sitemap과 Page가 같을 경우 ValidationError 발생
        if self.parent_sitemap_id and self.parent_sitemap_id == self.id:
            raise ValidationError("자기 자신을 부모로 설정할 수 없습니다.")

        # 순환 참조를 방지하기 위해 Parent Sitemap이 자식 Sitemap을 가리키는 경우 ValidationError 발생
        parent_sitemap = self.parent_sitemap
        while parent_sitemap:
            if parent_sitemap == self:
                raise ValidationError("Parent Sitemap이 자식 Sitemap을 가리킬 수 없습니다.")
            parent_sitemap = parent_sitemap.parent_sitemap

        # route를 계산할 시 이미 존재하는 route가 있을 경우 ValidationError 발생
        # (도메인 그룹이 다르면 같은 route_code 허용 — 그룹 내에서만 검증)
        if self.domain_group_id and self.route in Sitemap.objects.get_all_routes(self.domain_group_id):
            raise ValidationError(f"`{self.route}`라우트는 이미 존재하는 route입니다.")


class Section(BaseAbstractModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    order = models.IntegerField(default=0)

    css = models.TextField(null=True, blank=True, default=None)
    body = MarkdownField(help_text="Content of the page, Written in markdown format")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Section {self.order} of {self.page}"
