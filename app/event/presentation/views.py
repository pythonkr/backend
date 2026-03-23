from core.const.tag import OpenAPITag
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from event.presentation.filters import PresentationFilterSet
from event.presentation.models import Presentation, PresentationCategory
from event.presentation.serializers import PresentationSerializer
from rest_framework import mixins, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PresentationCategory.objects.filter_active()


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet
