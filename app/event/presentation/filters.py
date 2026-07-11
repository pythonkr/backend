from enum import StrEnum

from core.models import BaseAbstractModelQuerySet
from django.db.models import Q
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES
from event.filters import EventFilterMixin
from event.presentation.models import PresentationBookmark
from rest_framework import exceptions


class PresentationBookmarkErrorCode(StrEnum):
    EVENT_NOT_FOUND = "event_not_found"


class PresentationFilterSet(EventFilterMixin):
    event_field_prefix = "type__event"
    types = filters.BaseCSVFilter(method="filter_by_type_names")

    def filter_by_type_names(self, queryset: BaseAbstractModelQuerySet, name: str, values: list[str]) -> Q:
        if values in EMPTY_VALUES:
            return queryset

        return queryset.filter(Q(type__name_ko__in=values) | Q(type__name_en__in=values))


class PresentationBookmarkFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(method="filter_by_event")

    class Meta:
        model = PresentationBookmark
        fields = ["event"]

    def filter_by_event(
        self, queryset: BaseAbstractModelQuerySet, name: str, values: list[str]
    ) -> BaseAbstractModelQuerySet:
        filtered_queryset = queryset.filter(presentation__type__event__id=values)
        if not filtered_queryset.exists():
            raise exceptions.NotFound(
                detail="해당 행사 정보가 없습니다.",
                code=PresentationBookmarkErrorCode.EVENT_NOT_FOUND,
            )
        return filtered_queryset
