from django.db.models import QuerySet
from django_filters import rest_framework as filters
from user.models.merge import UserMergeHistory


class UserMergeAdminFilterSet(filters.FilterSet):
    reverted = filters.BooleanFilter(method="filter_reverted")

    class Meta:
        model = UserMergeHistory
        fields = ["source", "target", "reverted"]

    def filter_reverted(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        return queryset.filter(reverted_at__isnull=not value)
