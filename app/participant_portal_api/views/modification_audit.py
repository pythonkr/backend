from core.const.tag import OpenAPITag
from django.db import models
from drf_spectacular import utils
from drf_standardized_errors.openapi_serializers import (
    ValidationErrorEnum,
    ValidationErrorResponseSerializer,
    ValidationErrorSerializer,
)
from event.presentation.models import Presentation
from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.modification_audit import (
    ModificationAuditCancelPortalSerializer,
    ModificationAuditResponsePortalSerializer,
)
from participant_portal_api.serializers.modification_audit_preview import (
    ModificationAuditPresentationPreviewPortalSerializer,
    ModificationAuditUserPreviewPortalSerializer,
)
from rest_framework import decorators, mixins, request, response, serializers, status, viewsets
from user.models import UserExt

MODEL_SERIALIZER_MAP: dict[models.Model, type[serializers.Serializer]] = {
    Presentation: ModificationAuditPresentationPreviewPortalSerializer,
    UserExt: ModificationAuditUserPreviewPortalSerializer,
}


@utils.extend_schema_view(
    list=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_MODIFICATION_AUDIT]),
    retrieve=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_MODIFICATION_AUDIT]),
)
class ModificationAuditPortalViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ModificationAuditResponsePortalSerializer
    permission_classes = [IsSessionSpeaker]
    queryset = (
        ModificationAudit.objects.filter_active()
        .prefetch_related(
            models.Prefetch("comments", queryset=ModificationAuditComment.objects.select_related("created_by"))
        )
        .select_related("created_by", "updated_by", "deleted_by")
    )

    def get_queryset(self):
        """본인이 요청한 수정 이력만 조회 가능하도록 필터링"""
        if not self.request.user.is_authenticated:
            return super().get_queryset().none()
        return super().get_queryset().filter(created_by=self.request.user)

    @utils.extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_MODIFICATION_AUDIT],
        request=ModificationAuditCancelPortalSerializer,
    )
    @decorators.action(detail=True, methods=["patch"], url_path="cancel")
    def cancel_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        """destroy 메소드를 사용하고 싶었으나, reason 필드를 받기 위해 patch 메소드를 사용합니다."""
        serializer = ModificationAuditCancelPortalSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=self.get_serializer(instance).data)

    @utils.extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_MODIFICATION_AUDIT],
        responses={
            status.HTTP_200_OK: ModificationAuditPresentationPreviewPortalSerializer,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
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
