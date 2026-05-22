from core.authz import IsSuperUser
from core.const.shop_error_messages import PermissionErrorMessages
from core.const.tag import OpenAPITag
from core.util.totp import TOTPInfo
from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import request, response, status, viewsets
from rest_framework.decorators import action


class RefundAuthorizerAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperUser]
    totp = TOTPInfo(key=settings.SHOP.refund_authorizer_secret_key.encode())

    @extend_schema(
        summary="TOTP otpauth URI 발급 (Google Authenticator 등에 등록)",
        tags=[OpenAPITag.ADMIN_SHOP_REFUND_AUTHORIZER],
        responses={status.HTTP_200_OK: {"type": "object", "properties": {"otpauth_url": {"type": "string"}}}},
    )
    @action(detail=False, methods=["get"], url_path="setup-qr")
    def setup_qr(self, request: request.Request) -> response.Response:
        issuer = f"PyConKR{':Local' if settings.IS_LOCAL else ':Dev' if settings.DEBUG else ':Prod'}"
        return response.Response({"otpauth_url": self.totp.get_otpauth_uri(issuer=issuer, username="Refund")})

    @extend_schema(
        summary="TOTP 코드 검증",
        tags=[OpenAPITag.ADMIN_SHOP_REFUND_AUTHORIZER],
        parameters=[
            OpenApiParameter(
                name="otp",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Google Authenticator 등에서 발급된 6자리 OTP 코드",
            ),
        ],
        responses={
            status.HTTP_200_OK: {"type": "object", "properties": {"valid": {"type": "boolean"}}},
            status.HTTP_400_BAD_REQUEST: {"type": "object", "properties": {"detail": {"type": "string"}}},
        },
    )
    @action(detail=False, methods=["post"], url_path="verify")
    def verify(self, request: request.Request) -> response.Response:
        if not (otp := request.query_params.get("otp", "")):
            return response.Response(
                {"detail": PermissionErrorMessages.OTP_REQUIRED}, status=status.HTTP_400_BAD_REQUEST
            )
        return response.Response({"valid": self.totp.check(otp)})
