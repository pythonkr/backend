from __future__ import annotations

from admin_api.serializers.event.event import EventAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.models import Event
from rest_framework import viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_EVENT]) for m in ADMIN_METHODS})
class EventAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = EventAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Event.objects.filter_active().select_related_with_user().order_by("-event_end_at", "pk")
