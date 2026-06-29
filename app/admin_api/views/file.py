from admin_api.filtersets.file import PublicFileAdminFilterSet
from admin_api.serializers.file import PublicFileAdmimUploadSerializer, PublicFileAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from drf_spectacular import utils
from file.models import PublicFile
from rest_framework import decorators, mixins, parsers, request, response, serializers, status, viewsets

ADMIN_METHODS = ["list", "retrieve", "destroy"]


@utils.extend_schema_view(**{m: utils.extend_schema(tags=[OpenAPITag.ADMIN_PUBLIC_FILE]) for m in ADMIN_METHODS})
class PublicFileAdminViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    JsonSchemaViewSet,
    viewsets.GenericViewSet,
):
    serializer_class = PublicFileAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = PublicFileAdminFilterSet
    queryset = PublicFile.objects.filter_active().select_related_with_user().order_by("-created_at", "pk")

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_PUBLIC_FILE],
        responses={status.HTTP_201_CREATED: PublicFileAdminSerializer},
    )
    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="upload",
        serializer_class=PublicFileAdmimUploadSerializer,
        parser_classes=[parsers.MultiPartParser, parsers.FileUploadParser],
    )
    def upload(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if "file" not in request.FILES:
            raise serializers.ValidationError({"file": "This field is required."})

        serializer = PublicFileAdmimUploadSerializer(data=request.FILES)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        file_data = PublicFileAdminSerializer(instance=instance).data
        return response.Response(data=file_data, status=status.HTTP_201_CREATED)
