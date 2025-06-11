from __future__ import annotations

import contextlib
import dataclasses
import datetime
import re
import typing

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Page(BaseAbstractModel):
    css = models.TextField(null=True, blank=True, default=None)
    title = models.CharField(max_length=256)
    subtitle = models.CharField(max_length=512)

    show_top_title_banner = models.BooleanField(default=False, help_text="페이지 상단에 타이틀 배너를 표시할지 여부")
    show_bottom_sponsor_banner = models.BooleanField(
        default=False, help_text="페이지 하단에 스폰서 배너를 표시할지 여부"
    )

    def __str__(self):
        return str(self.title)

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

    @property
    def route(self) -> str:
        if self.parent:
            return f"{self.parent.route}/{self.route_code}"
        return self.route_code


class SitemapQuerySet(BaseAbstractModelQuerySet):
    def filter_by_today(self) -> typing.Self:
        now = datetime.datetime.now()
        return self.filter(
            models.Q(display_start_at__isnull=True) | models.Q(display_start_at__lte=now),
            models.Q(display_end_at__isnull=True) | models.Q(display_end_at__gte=now),
        )

    def get_all_routes(self) -> set[str]:
        flattened_graph: dict[str, SitemapGraph] = {
            id: SitemapGraph(id=id, parent_id=parent_id, route_code=route_code)
            for id, parent_id, route_code in self.all().values_list("id", "parent_sitemap_id", "route_code")
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
    parent_sitemap = models.ForeignKey(
        "self", null=True, blank=True, default=None, on_delete=models.SET_NULL, related_name="children"
    )

    route_code = models.CharField(max_length=256, blank=True)
    name = models.CharField(max_length=256)
    order = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    page = models.ForeignKey(Page, on_delete=models.PROTECT)
    hide = models.BooleanField(default=False, help_text="이 Sitemap을 숨길지 여부")

    display_start_at = models.DateTimeField(null=True, blank=True)
    display_end_at = models.DateTimeField(null=True, blank=True)

    objects: SitemapQuerySet = SitemapQuerySet.as_manager()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.route} ({self.name})"

    @property
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
        if self.route in Sitemap.objects.get_all_routes():
            raise ValidationError(f"`{self.route}`라우트는 이미 존재하는 route입니다.")


class Section(BaseAbstractModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    order = models.IntegerField(default=0)

    css = models.TextField(null=True, blank=True, default=None)
    body = models.TextField(help_text="Content of the page, Written in markdown format")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Section {self.order} of {self.page}"
