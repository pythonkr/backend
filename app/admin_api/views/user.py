from admin_api.serializers.user import (
    OrganizationAdminSerializer,
    UserAdminPasswordChangeSerializer,
    UserAdminPasswordResetResponseSerializer,
    UserAdminSerializer,
    UserAdminSignInSerializer,
)
from core.const.account import generate_random_password
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.contrib.auth import login, logout
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, mixins, request, response, status, viewsets
from user.models import UserExt
from user.models.organization import Organization

ADMIN_METHODS = ["list", "retrieve", "create", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_USER]) for m in ADMIN_METHODS})
class UserAdminViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    JsonSchemaViewSet,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = UserAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = UserExt.objects.filter(is_active=True)

    def create(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        data = serializer.data
        data["password"] = serializer._generated_password
        headers = self.get_success_headers(data)
        return response.Response(data=data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(tags=[OpenAPITag.ADMIN_ACCOUNT], responses={status.HTTP_200_OK: UserAdminSerializer})
    @decorators.action(detail=False, methods=["GET"], permission_classes=[])
    def me(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not request.user.is_authenticated:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        return response.Response(data=UserAdminSerializer(request.user).data)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_ACCOUNT],
        request=UserAdminSignInSerializer,
        responses={status.HTTP_200_OK: UserAdminSerializer},
    )
    @decorators.action(detail=False, methods=["POST"], url_path="signin", permission_classes=[])
    def signin(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = UserAdminSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login(request=request, user=serializer.user)
        return response.Response(data=UserAdminSerializer(serializer.user).data)

    @extend_schema(tags=[OpenAPITag.ADMIN_ACCOUNT], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["DELETE"], url_path="signout", permission_classes=[])
    def signout(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        logout(request=request)
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_USER],
        responses={status.HTTP_200_OK: UserAdminPasswordResetResponseSerializer},
    )
    @decorators.action(detail=True, methods=["DELETE"], url_path="password")
    def reset_password(self, *args: tuple, **kwargs: dict) -> response.Response:
        new_password = generate_random_password()

        user: UserExt = self.get_object()
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return response.Response(
            data={"password": new_password},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=[OpenAPITag.ADMIN_ACCOUNT],
        request=UserAdminPasswordChangeSerializer,
        responses={status.HTTP_200_OK: UserAdminSerializer},
    )
    @decorators.action(detail=False, methods=["POST"], url_path="password", permission_classes=[IsSuperUser])
    def change_password(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = UserAdminPasswordChangeSerializer(data=request.data, instance=request.user)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(data=UserAdminSerializer(serializer.instance).data)


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_USER]) for m in ADMIN_METHODS})
class OrganizationAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = OrganizationAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Organization.objects.filter_active()
