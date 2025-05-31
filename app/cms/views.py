from cms.models import Page, Sitemap
from cms.serializers import PageSerializer, SitemapSerializer
from core.const.tag import OpenAPITag
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.CMS]))
class SitemapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SitemapSerializer
    queryset = Sitemap.objects.filter_active().filter_by_today()


@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.CMS]))
class PageViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.filter_active().prefetch_related("sections")
