from urllib.parse import urlparse

from cms.models import Page, Section, Sitemap
from cms.serializers import PageSerializer, SitemapSerializer
from core.const.tag import OpenAPITag
from django.db import models
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, mixins, viewsets


@method_decorator(
    name="list",
    decorator=extend_schema(
        tags=[OpenAPITag.CMS],
        parameters=[
            OpenApiParameter(
                name="frontend-domain",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Sitemap이 노출될 frontend 도메인.\n"
                    "이 값이 없으면 X-Frontend-Domain 헤더 → Origin → Referer 순으로 도메인을 결정합니다.\n"
                    "도메인을 결정할 수 없으면 404를 반환합니다.\n"
                    "도메인은 결정되었으나 매칭되는 그룹이 없으면 빈 결과를 반환합니다."
                ),
            ),
        ],
    ),
)
class SitemapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SitemapSerializer

    def get_queryset(self):
        raw = (
            (
                self.request.query_params.get("frontend-domain")
                or self.request.headers.get("X-Frontend-Domain")
                or self.request.headers.get("Origin")
                or self.request.headers.get("Referer")
                or ""
            )
            .strip()
            .lower()
        )
        if not (host := urlparse(raw).hostname if "://" in raw else raw.split("/", 1)[0].split(":", 1)[0]):
            raise exceptions.NotFound("frontend 도메인을 결정할 수 없습니다.")
        return Sitemap.objects.filter_active().filter_by_today().filter_by_domain(host)


@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.CMS]))
class PageViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.filter_active().prefetch_related(
        models.Prefetch(
            lookup="sections",
            queryset=Section.objects.filter_active().order_by("order"),
            to_attr="_prefetched_active_sections",
        )
    )
