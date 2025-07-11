from admin_api.serializers.modification_audit import (
    ModificationAuditApprovalAdminSerializer,
    ModificationAuditRejectionAdminSerializer,
    ModificationAuditResponseAdminSerializer,
    PresentationModificationAuditPreviewAdminSerializer,
    UserModificationAuditPreviewAdminSerializer,
)
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from django.db import models
from drf_spectacular import utils
from drf_standardized_errors.openapi_serializers import (
    ValidationErrorEnum,
    ValidationErrorResponseSerializer,
    ValidationErrorSerializer,
)
from event.presentation.models import Presentation
from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from rest_framework import decorators, mixins, request, response, serializers, status, viewsets
from user.models import UserExt

MODEL_SERIALIZER_MAP: dict[models.Model, type[serializers.Serializer]] = {
    Presentation: PresentationModificationAuditPreviewAdminSerializer,
    UserExt: UserModificationAuditPreviewAdminSerializer,
}


@utils.extend_schema_view(
    list=utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT]),
    retrieve=utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT]),
)
class ModificationAuditAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ModificationAuditResponseAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        ModificationAudit.objects.filter_active()
        .prefetch_related(
            models.Prefetch("comments", queryset=ModificationAuditComment.objects.select_related("created_by"))
        )
        .select_related("created_by", "updated_by", "deleted_by")
    )

    @utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT])
    @decorators.action(detail=True, methods=["get"], url_path="preview")
    def preview_modification_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        audit: ModificationAudit = self.get_object()

        if serializer := MODEL_SERIALIZER_MAP.get(audit.instance_type.model_class()):
            return response.Response(data=serializer(audit, context={"request": request}).data)

        return response.Response(
            data=ValidationErrorResponseSerializer(
                instance={
                    "type": ValidationErrorEnum.VALIDATION_ERROR,
                    "errors": ValidationErrorSerializer(
                        instance=[
                            {
                                "code": "modification_audit_preview_error",
                                "detail": f"지원하지 않는 모델: {audit.instance_type.model_class().__name__}",
                                "attr": "instance",
                            }
                        ],
                        many=True,
                    ).data,
                },
            ).data,
            status=status.HTTP_400_BAD_REQUEST,
        )

    @utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT])
    @decorators.action(detail=True, methods=["patch"], url_path="approve")
    def approve_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = ModificationAuditApprovalAdminSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=self.get_serializer(instance).data)

    @utils.extend_schema(tags=[OpenAPITag.ADMIN_MODIFICATION_AUDIT])
    @decorators.action(detail=True, methods=["patch"], url_path="reject")
    def reject_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = ModificationAuditRejectionAdminSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=self.get_serializer(instance).data)
