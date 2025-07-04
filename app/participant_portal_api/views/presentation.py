import typing

from core.const.tag import OpenAPITag
from drf_spectacular import utils
from event.presentation.models import Presentation, PresentationSpeaker
from participant_portal_api.models import ModificationAudit
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.presentation import PresentationPortalSerializer
from rest_framework import decorators, mixins, request, response, status, viewsets


@utils.extend_schema_view(
    list=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_PRESENTATION]),
    retrieve=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_PRESENTATION]),
    partial_update=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_PRESENTATION]),
)
class PresentationPortalViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PresentationPortalSerializer
    queryset = Presentation.objects.filter_active().get_all_nested_data().order_by("-created_at")
    permission_classes = [IsSessionSpeaker]
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        """본인의 발표만 조회 가능하도록 필터링"""
        if not self.request.user.is_authenticated:
            return super().get_queryset().none()

        return (
            super()
            .get_queryset()
            .filter(
                id__in=PresentationSpeaker.objects.filter(
                    user=self.request.user,
                    presentation__deleted_at__isnull=True,
                ).values_list("presentation_id", flat=True),
            )
        )

    @utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_PRESENTATION])
    @decorators.action(detail=True, methods=["get"], url_path="preview")
    def preview_modification_audit(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not (
            mod_audit := typing.cast(
                ModificationAudit | None, ModificationAudit.objects.filter_requested(self.get_object()).first()
            )
        ):
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        return response.Response(data=self.get_serializer(mod_audit.apply_modification(save=False)).data)
