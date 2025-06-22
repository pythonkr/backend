from __future__ import annotations

from admin_api.filtersets.event.presentation import (
    PresentationAdminFilterSet,
    PresentationCategoryAdminFilterSet,
    PresentationSpeakerAdminFilterSet,
)
from admin_api.serializers.event.presentation import (
    PresentationAdminSerializer,
    PresentationCategoryAdminSerializer,
    PresentationSpeakerAdminSerializer,
    PresentationTypeAdminSerializer,
)
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationSpeaker,
    PresentationType,
)
from rest_framework import viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationTypeAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationTypeAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = PresentationType.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationCategoryAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationCategoryAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationCategoryAdminFilterSet
    queryset = PresentationCategory.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationAdminFilterSet
    queryset = Presentation.objects.get_all_nested_data().select_related("created_by", "updated_by", "deleted_by")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationSpeakerAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationSpeakerAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationSpeakerAdminFilterSet
    queryset = PresentationSpeaker.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")
