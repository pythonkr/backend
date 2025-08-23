from logging import getLogger

from core.util.google_api import create_authorization_url, create_oauth_flow, fetch_credentials
from django.shortcuts import redirect
from drf_standardized_errors.openapi_serializers import (
    ErrorCode500Enum,
    ErrorResponse500Serializer,
    ServerErrorEnum,
    ValidationErrorEnum,
    ValidationErrorResponseSerializer,
)
from external_api.google_oauth2.models import GoogleOAuth2
from rest_framework import decorators, permissions, request, response, status, viewsets
from user.models import UserExt

logger = getLogger(__name__)


class GoogleOAuth2ViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _response_400(code: str, detail: str) -> response.Response:
        return response.Response(
            status=status.HTTP_400_BAD_REQUEST,
            data=ValidationErrorResponseSerializer(
                instance={
                    "type": ValidationErrorEnum.VALIDATION_ERROR,
                    "errors": [{"code": code, "detail": detail, "attr": None}],
                }
            ).data,
        )

    @staticmethod
    def _response_500(detail: str) -> response.Response:
        return response.Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data=ErrorResponse500Serializer(
                instance={
                    "type": ServerErrorEnum.SERVER_ERROR,
                    "errors": [{"code": ErrorCode500Enum.ERROR, "detail": detail, "attr": None}],
                }
            ).data,
        )

    @decorators.action(detail=False, methods=["get"], url_path="authorize", url_name="authorize")
    def authorize_google_oauth2(self, *args: tuple, **kwargs: dict) -> response.Response:
        if not (flow := create_oauth_flow()):
            return self._response_500("Google OAuth is not configured.")

        return redirect(create_authorization_url(flow=flow))

    @decorators.action(detail=False, methods=["get"], url_path="redirect", url_name="redirect")
    def redirect_google_oauth2(self, request: request.Request, *args, **kwargs) -> response.Response:
        if not (code := request.query_params.get("code")):
            return self._response_400("missing_code", "The 'code' query parameter is required.")

        if not (flow := create_oauth_flow()):
            return self._response_500("Google OAuth is not configured.")

        try:
            refresh_token = fetch_credentials(flow, code).refresh_token
            system = UserExt.get_system_user()
            GoogleOAuth2.objects.get_or_create(refresh_token=refresh_token, created_by=system, modified_by=system)
            return response.Response({"detail": "Google OAuth setup completed successfully."})
        except Exception as e:
            logger.error(f"Failed to fetch Google OAuth2 credentials: {e}", exc_info=e)
            return self._response_400(f"Failed to fetch credentials: {e}")
