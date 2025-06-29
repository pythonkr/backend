from core.const.tag import OpenAPITag
from django.db import models
from drf_spectacular import utils
from file.models import PublicFile
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.file import PublicFilePortalSerializer, PublicFilePortalUploadSerializer
from rest_framework import decorators, mixins, parsers, request, response, serializers, status, viewsets


@utils.extend_schema_view(list=utils.extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_PUBLIC_FILE]))
class PublicFilePortalViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PublicFilePortalSerializer
    queryset = PublicFile.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")
    permission_classes = [IsSessionSpeaker]

    def get_queryset(self) -> models.QuerySet[PublicFile]:
        """본인이 업로드한 파일만 조회 가능하도록 필터링"""
        if not self.request.user.is_authenticated:
            return super().get_queryset().none()
        return (
            super()
            .get_queryset()
            .filter(models.Q(created_by=self.request.user) | models.Q(updated_by=self.request.user))
        )

    @utils.extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_PUBLIC_FILE],
        responses={status.HTTP_201_CREATED: PublicFilePortalSerializer},
    )
    @decorators.action(
        detail=False,
        methods=["POST"],
        url_path="upload",
        serializer_class=PublicFilePortalUploadSerializer,
        parser_classes=[parsers.MultiPartParser, parsers.FileUploadParser],
    )
    def upload(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if "file" not in request.FILES:
            raise serializers.ValidationError({"file": "This field is required."})

        serializer = PublicFilePortalUploadSerializer(data=request.FILES)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=PublicFilePortalUploadSerializer(instance).data, status=status.HTTP_201_CREATED)
