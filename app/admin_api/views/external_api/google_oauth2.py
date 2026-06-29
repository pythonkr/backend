from admin_api.serializers.external_api.google_oauth2 import (
    GoogleOAuth2AdminAccessTokenSerializer,
    GoogleOAuth2AdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from external_api.google_oauth2.models import GoogleOAuth2
from rest_framework import decorators, request, response, status, viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EXT_API_GOOGLE_OAUTH2]) for m in ADMIN_METHODS})
class GoogleOAuth2AdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = GoogleOAuth2AdminSerializer
    permission_classes = [IsSuperUser]
    queryset = GoogleOAuth2.objects.filter_active().select_related_with_user().order_by("-created_at", "pk")

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EXT_API_GOOGLE_OAUTH2],
        request=None,
        responses={status.HTTP_200_OK: GoogleOAuth2AdminAccessTokenSerializer},
    )
    @decorators.action(detail=True, methods=["post"], url_path="access-token")
    def issue_access_token(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        data = GoogleOAuth2AdminAccessTokenSerializer(instance=self.get_object()).data
        if not data["is_valid"]:
            return response.Response(
                data={"detail": f"Failed to issue access token: {data['error']}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return response.Response(data=data)
