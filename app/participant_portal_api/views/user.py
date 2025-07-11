from core.const.tag import OpenAPITag
from django.contrib.auth import login, logout
from drf_spectacular.utils import extend_schema
from participant_portal_api.models import ModificationAudit
from participant_portal_api.permissions import IsSessionSpeaker
from participant_portal_api.serializers.user import (
    UserPortalPasswordChangeSerializer,
    UserPortalSerializer,
    UserPortalSignInSerializer,
)
from rest_framework import decorators, request, response, status, viewsets
from user.models import UserExt


class UserPortalViewSet(viewsets.GenericViewSet):
    serializer_class = UserPortalSerializer
    queryset = UserExt.objects.filter(is_active=True)
    permission_classes = [IsSessionSpeaker]

    @extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_USER],
        responses={status.HTTP_200_OK: UserPortalSerializer},
    )
    @decorators.action(detail=False, methods=["get"], url_path="me")
    def retrieve_profile(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not request.user.is_authenticated:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        user = request.user
        serializer_class = self.get_serializer_class()

        if audit := ModificationAudit.objects.filter_requested(user).first():
            data = serializer_class(audit.fake_modified_instance, context={"request": self.request}).data
        else:
            data = serializer_class(user).data

        return response.Response(data=data)

    @extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_USER],
        responses={status.HTTP_200_OK: UserPortalSerializer},
    )
    @retrieve_profile.mapping.patch
    def patch_profile(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not request.user.is_authenticated:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=UserPortalSerializer(instance).data)

    @extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_USER],
        request=UserPortalSignInSerializer,
        responses={status.HTTP_200_OK: UserPortalSerializer},
    )
    @decorators.action(detail=False, methods=["post"], url_path="signin")
    def signin(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = UserPortalSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login(request=request, user=serializer.user)
        return response.Response(data=UserPortalSerializer(serializer.user).data)

    @extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_USER], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["delete"], url_path="signout")
    def signout(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        logout(request=request)
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=[OpenAPITag.PARTICIPANT_PORTAL_USER],
        request=UserPortalPasswordChangeSerializer,
        responses={status.HTTP_200_OK: UserPortalSerializer},
    )
    @decorators.action(detail=False, methods=["put"], url_path="password")
    def change_password(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = UserPortalPasswordChangeSerializer(data=request.data, instance=request.user)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(data=UserPortalSerializer(request.user).data)
