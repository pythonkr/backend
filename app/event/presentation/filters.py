from core.models import BaseAbstractModelQuerySet
from django.db.models import Q
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES
from event.filters import EventFilterMixin


class PresentationFilterSet(EventFilterMixin):
    event_field_prefix = "type__event"
    types = filters.BaseCSVFilter(method="filter_by_type_names")

    def filter_by_type_names(self, queryset: BaseAbstractModelQuerySet, name: str, values: list[str]) -> Q:
        if values in EMPTY_VALUES:
            return queryset

        return queryset.filter(Q(type__name_ko__in=values) | Q(type__name_en__in=values))
