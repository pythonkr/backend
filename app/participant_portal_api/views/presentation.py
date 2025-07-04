from core.const.tag import OpenAPITag
from drf_spectacular import utils
from event.presentation.models import Presentation, PresentationSpeaker
from participant_portal_api.models import ModificationAudit
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.presentation import PresentationPortalSerializer
from rest_framework import mixins, viewsets


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

    def get_object(self):
        presentation = super().get_object()
        if mod_audit := ModificationAudit.objects.filter_requested(presentation).first():
            presentation = mod_audit.apply_modification(save=False)

        return presentation
