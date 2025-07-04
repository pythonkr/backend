from admin_api.serializers.modification_audit import (
    ModificationAuditApprovalAdminSerializer,
    ModificationAuditRejectionAdminSerializer,
    ModificationAuditResponseAdminSerializer,
)
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from django.db import models
from drf_spectacular import utils
from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from rest_framework import decorators, mixins, request, response, status, viewsets


@utils.extend_schema_view(
    list=utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT]),
    retrieve=utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT]),
)
class ModificationAuditAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ModificationAuditResponseAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        ModificationAudit.objects.filter_active()
        .prefetch_related(
            models.Prefetch("comments", queryset=ModificationAuditComment.objects.select_related("created_by"))
        )
        .select_related("created_by", "updated_by", "deleted_by")
    )

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT],
        responses={status.HTTP_200_OK: ModificationAuditApprovalAdminSerializer},
    )
    @decorators.action(detail=True, methods=["patch"], url_path="aprove")
    def cancel_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = ModificationAuditApprovalAdminSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=self.get_serializer(instance).data)

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT],
        responses={status.HTTP_200_OK: ModificationAuditRejectionAdminSerializer},
    )
    @decorators.action(detail=True, methods=["patch"], url_path="reject")
    def reject_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = ModificationAuditRejectionAdminSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=self.get_serializer(instance).data)
