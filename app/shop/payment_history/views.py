import logging
import typing

from core.const.tag import OpenAPITag
from core.logger.util.decorator import bad_response_slack_logger
from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_standardized_errors.openapi_serializers import ValidationErrorResponseSerializer
from rest_framework import exceptions, mixins, permissions, request, response, status, viewsets
from shop.payment_history.models import PaymentHistory, PaymentWebhookEvent
from shop.payment_history.serializers import PortOneV1WebhookRequestSerializer, PortOneV1WebhookResponseSerializer

logger = logging.getLogger(__name__)


def _get_client_ip(request: request.Request) -> str | None:
    if xff := request.META.get("HTTP_X_FORWARDED_FOR", ""):
        return xff.split(",")[0].strip()
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")


class PaymentHistoryViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = PaymentHistory.objects.all()
    serializer_class = PortOneV1WebhookRequestSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="PortOne 결제 Webhook",
        tags=[OpenAPITag.SHOP_PORTONE_WEBHOOK],
        responses={
            status.HTTP_200_OK: PortOneV1WebhookResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
    @bad_response_slack_logger(tag="PortOne 결제 결과 Webhook")
    def create(  # type: ignore[override]
        self, request: request.Request, *args: typing.Any, **kwargs: typing.Any
    ) -> response.Response:
        if not (settings.DEBUG or _get_client_ip(request) in settings.PORTONE.ip_list):
            raise exceptions.PermissionDenied()

        logger.info(f"PortOne Webhook Request: {request.data}")
        PaymentWebhookEvent.objects.create(
            event_type=PaymentWebhookEvent.EventType.WEBHOOK_RECEIVED,
            request_payload=dict(request.data),
        )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return response.Response(data={"status": "success", "message": "일반 결제 성공"})
