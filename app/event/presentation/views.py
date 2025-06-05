from django_filters import rest_framework as filters
from event.presentation.models import Presentation
from event.presentation.serializers import PresentationSerializer
from rest_framework import mixins, viewsets


class PresentationFilterSet(filters.FilterSet):
    category = filters.CharFilter(field_name="presentation_categories__name", lookup_expr="exact")


class PresentationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet
