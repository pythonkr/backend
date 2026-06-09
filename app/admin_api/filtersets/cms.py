from cms.models import Page
from django_filters import rest_framework as filters


class PageAdminFilterSet(filters.FilterSet):
    title = filters.CharFilter(lookup_expr="icontains")
    subtitle = filters.CharFilter(lookup_expr="icontains")
    created_at__year = filters.NumberFilter(field_name="created_at", lookup_expr="year")

    class Meta:
        model = Page
        fields = ["title", "subtitle", "show_top_title_banner", "show_bottom_sponsor_banner"]
