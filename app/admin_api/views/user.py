from admin_api.serializers.user import UserAdminSerializer, UserAdminSignInSerializer
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.contrib.auth import login, logout
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, request, response, status, viewsets
from user.models import UserExt

ADMIN_METHODS = ["list", "retrieve", "create", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_USER]) for m in ADMIN_METHODS})
class UserAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = UserAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = UserExt.objects.filter(is_active=True)

    @extend_schema(tags=[OpenAPITag.ADMIN_USER], responses={status.HTTP_200_OK: UserAdminSerializer})
    @decorators.action(detail=False, methods=["GET"], permission_classes=[])
    def me(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not request.user.is_authenticated:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        return response.Response(data=UserAdminSerializer(request.user).data)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_USER],
        request=UserAdminSignInSerializer,
        responses={status.HTTP_200_OK: UserAdminSerializer},
    )
    @decorators.action(detail=False, methods=["POST"], url_path="signin", permission_classes=[])
    def signin(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = UserAdminSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login(request=request, user=serializer.user)
        return response.Response(data=UserAdminSerializer(serializer.user).data)

    @extend_schema(tags=[OpenAPITag.ADMIN_USER], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["DELETE"], url_path="signout", permission_classes=[])
    def signout(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        logout(request=request)
        return response.Response(status=status.HTTP_204_NO_CONTENT)
