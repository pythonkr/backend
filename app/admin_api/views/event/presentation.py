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
from core.const.regex import UUID_V4_REGEX
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
from participant_portal_api.models import ModificationAudit
from rest_framework import decorators, request, response, status, viewsets

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

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION])
    @decorators.action(detail=True, methods=["get"], url_path=r"preview/(?P<audit_id>[\w-]+)")
    def preview_modification_audit(
        self, request: request.Request, audit_id: str, *args: tuple, **kwargs: dict
    ) -> response.Response:
        if not UUID_V4_REGEX.match(audit_id):
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        if not (audit := ModificationAudit.objects.filter_by_instance(self.get_object()).filter(id=audit_id).first()):
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        return response.Response(data=audit.get_applied_data(serializer_class=self.get_serializer_class()))


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationSpeakerAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationSpeakerAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PresentationSpeakerAdminFilterSet
    queryset = PresentationSpeaker.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION])
    @decorators.action(detail=True, methods=["get"], url_path=r"preview/(?P<audit_id>[\w-]+)")
    def preview_modification_audit(
        self, request: request.Request, audit_id: str, *args: tuple, **kwargs: dict
    ) -> response.Response:
        if not UUID_V4_REGEX.match(audit_id):
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        if not (audit := ModificationAudit.objects.filter_by_instance(self.get_object()).filter(id=audit_id).first()):
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        return response.Response(data=audit.get_applied_data(serializer_class=self.get_serializer_class()))
