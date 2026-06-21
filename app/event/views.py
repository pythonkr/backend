from core.const.tag import OpenAPITag
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from event.models import Event
from event.serializers import EventSerializer
from rest_framework import mixins, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT]))
class EventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Event.objects.filter_active()
    serializer_class = EventSerializer
