from django_filters import rest_framework as filters
from file.models import PublicFile


class PublicFileAdminFilterSet(filters.FilterSet):
    mimetype = filters.CharFilter(lookup_expr="icontains")
    hash = filters.CharFilter(lookup_expr="iexact")
    created_at__year = filters.NumberFilter(field_name="created_at", lookup_expr="year")
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = PublicFile
        fields = ["mimetype", "hash", "created_by", "created_after", "created_before"]
