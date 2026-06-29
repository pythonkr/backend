from __future__ import annotations

from admin_api.filtersets.event.presentation import (
    PresentationAdminFilterSet,
    PresentationCategoryAdminFilterSet,
    PresentationSpeakerAdminFilterSet,
    PresentationTypeAdminFilterSet,
    RoomAdminFilterSet,
    RoomScheduleAdminFilterSet,
)
from admin_api.serializers.event.presentation import (
    PresentationAdminSerializer,
    PresentationCategoryAdminSerializer,
    PresentationSpeakerAdminSerializer,
    PresentationTypeAdminSerializer,
    RoomAdminSerializer,
    RoomScheduleAdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationSpeaker,
    PresentationType,
    Room,
    RoomSchedule,
)
from rest_framework import viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationTypeAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationTypeAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationTypeAdminFilterSet
    queryset = (
        PresentationType.objects.filter_active()
        .select_related_with_user("event")
        .order_by("-event__event_end_at", "-created_at", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationCategoryAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationCategoryAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationCategoryAdminFilterSet
    queryset = (
        PresentationCategory.objects.filter_active()
        .select_related_with_user("type", "type__event")
        .order_by("-type__event__event_end_at", "-created_at", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationAdminFilterSet
    queryset = (
        Presentation.objects.filter_active()
        .select_related_with_user("type", "type__event")
        .prefetch_related("categories")
        .order_by("-type__event__event_end_at", "title", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationSpeakerAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationSpeakerAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationSpeakerAdminFilterSet
    queryset = (
        PresentationSpeaker.objects.filter_active().select_related_with_user("user").order_by("user__username", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class RoomAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = RoomAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = RoomAdminFilterSet
    queryset = Room.objects.filter_active().select_related_with_user("event").order_by("-event__event_end_at", "pk")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class RoomScheduleAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = RoomScheduleAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = RoomScheduleAdminFilterSet
    queryset = (
        RoomSchedule.objects.filter_active()
        .select_related_with_user("room", "room__event")
        .order_by("-room__event__event_end_at", "end_at", "pk")
    )
