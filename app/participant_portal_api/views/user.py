from core.const.tag import OpenAPITag
from django.contrib.auth import logout
from drf_spectacular.utils import extend_schema
from participant_portal_api.models import ModificationAudit
from participant_portal_api.serializers.user import UserPortalSerializer
from rest_framework import decorators, permissions, request, response, status, viewsets
from user.models import UserExt


class UserPortalViewSet(viewsets.GenericViewSet):
    serializer_class = UserPortalSerializer
    queryset = UserExt.objects.filter(is_active=True)

    @extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_USER], responses={status.HTTP_200_OK: UserPortalSerializer})
    @decorators.action(detail=False, methods=["get"], url_path="me", permission_classes=[permissions.IsAuthenticated])
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

    @extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_USER], responses={status.HTTP_200_OK: UserPortalSerializer})
    @retrieve_profile.mapping.patch
    def patch_profile(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not request.user.is_authenticated:
            return response.Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        return response.Response(data=UserPortalSerializer(instance).data)

    @extend_schema(tags=[OpenAPITag.PARTICIPANT_PORTAL_USER], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["delete"], url_path="signout")
    def signout(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        logout(request=request)
        return response.Response(status=status.HTTP_204_NO_CONTENT)
