from cms.models import Page, Sitemap
from cms.serializers import PageSerializer, SitemapSerializer
from rest_framework import mixins, viewsets


class SitemapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SitemapSerializer
    queryset = Sitemap.objects.filter_active().filter_by_today()


class PageViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.filter_active().prefetch_related("sections")
