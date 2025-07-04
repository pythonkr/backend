from core.const.tag import OpenAPITag
from django.db import models
from drf_spectacular import utils
from participant_portal_api.models import ModificationAudit, ModificationAuditComment
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.modification_audit import (
    ModificationAuditCancelPortalSerializer,
    ModificationAuditResponsePortalSerializer,
)
from rest_framework import decorators, mixins, request, response, viewsets


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
