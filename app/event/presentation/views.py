from core.const.regex import UUID_V4
from django.db.models import QuerySet
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES
from event.presentation.models import Presentation, PresentationCategory, PresentationCategoryRelation
from event.presentation.serializers import PresentationSerializer
from rest_framework import mixins, serializers, viewsets


class PresentationFilterSet(filters.FilterSet):
    type = filters.UUIDFilter(field_name="type_id")
    categories = filters.BaseCSVFilter(method="filter_by_category_ids")

    def filter_by_category_ids(self, queryset: QuerySet, name: str, value: list[str]) -> QuerySet:
        if not value or value in EMPTY_VALUES:
            return queryset
        if not any(UUID_V4.match(v) for v in value):
            return serializers.ValidationError(f"Invalid UUID format in {name} filter: {value}.")

        target_ids = PresentationCategoryRelation.objects.filter(category__id__in=value).values_list("presentation_id")
        return queryset.filter(id__in=target_ids)


class PresentationCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PresentationCategory.objects.filter_active()


class PresentationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet
