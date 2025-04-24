from cms.models import Page, Sitemap
from cms.serializers import PageSerializer, SitemapSerializer
from rest_framework.viewsets import ReadOnlyModelViewSet


class SitemapListRetrieveViewSet(ReadOnlyModelViewSet):
    serializer_class = SitemapSerializer
    queryset = Sitemap.objects.all()


class PageListRetrieveViewSet(ReadOnlyModelViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.all()
