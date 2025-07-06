from core.const.tag import OpenAPITag
from core.models import BaseAbstractModelQuerySet
from django.db.models import Q
from django.utils.decorators import method_decorator
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES
from drf_spectacular.utils import extend_schema
from event.presentation.models import Presentation, PresentationCategory
from event.presentation.serializers import PresentationSerializer
from rest_framework import mixins, viewsets


class PresentationFilterSet(filters.FilterSet):
    event = filters.CharFilter(method="filter_by_event_name")
    types = filters.BaseCSVFilter(method="filter_by_type_names")

    def filter_by_event_name(self, queryset: BaseAbstractModelQuerySet, name: str, value: str) -> Q:
        if value in EMPTY_VALUES:
            return queryset

        return queryset.filter(Q(type__event__name_ko=value) | Q(type__event__name_en=value))

    def filter_by_type_names(self, queryset: BaseAbstractModelQuerySet, name: str, values: list[str]) -> Q:
        if values in EMPTY_VALUES:
            return queryset

        return queryset.filter(Q(type__name_ko__in=values) | Q(type__name_en__in=values))


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PresentationCategory.objects.filter_active()


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet
