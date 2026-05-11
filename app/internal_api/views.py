import typing

from core.authn.api_key import APIKeyAuthentication
from core.authz.api_key import RegistrationDeskAPIKeyPermission
from core.const.tag import OpenAPITag
from django.db import models, transaction
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from drf_standardized_errors.openapi_serializers import (
    Error403Serializer,
    Error404Serializer,
    ValidationErrorResponseSerializer,
)
from internal_api.filters import DeskSupportFilterSet
from internal_api.serializers import DeskSupportSerializer
from rest_framework import mixins, request, response, status, viewsets
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory
from shop.serializers.refund import OrderTotalRefundSerializer


@method_decorator(
    name="list",
    decorator=extend_schema(
        summary="주문 검색",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: DeskSupportSerializer(many=True),
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    ),
)
@method_decorator(
    name="partial_update",
    decorator=extend_schema(
        summary="주문 수정",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: DeskSupportSerializer,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
            status.HTTP_404_NOT_FOUND: Error404Serializer,
        },
    ),
)
@method_decorator(name="partial_update", decorator=transaction.atomic)
class DeskSupportViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Order.objects.filter_has_payment_histories()
        .select_related("customer_info")
        .prefetch_related(
            models.Prefetch(
                lookup="products",
                queryset=(
                    OrderProductRelation.objects.filter_active()
                    .select_related("product")
                    .prefetch_related(
                        models.Prefetch(
                            lookup="options",
                            queryset=OrderProductOptionRelation.objects.filter_active().select_related(
                                "product_option_group", "product_option"
                            ),
                        )
                    )
                ),
            ),
            models.Prefetch(
                "payment_histories",
                queryset=PaymentHistory.objects.filter_active().order_by("-created_at"),
                to_attr="_payment_histories_by_latest",
            ),
        )
        .order_by("-created_at")
    )
    filterset_class = DeskSupportFilterSet
    serializer_class = DeskSupportSerializer
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [RegistrationDeskAPIKeyPermission]
    http_method_names = ["get", "patch", "delete"]

    @extend_schema(
        summary="주문 전체 환불",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        parameters=[
            OpenApiParameter(
                name="otp",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                allow_blank=False,
                required=True,
            ),
        ],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
            status.HTTP_404_NOT_FOUND: Error404Serializer,
        },
    )
    @transaction.atomic
    def destroy(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """
        Order의 사용 및 환불하지 않은 상품을 refunded 상태로 변경하고, 결제 취소를 요청합니다.
        일반 전체 환불 API와의 차이점은, 환불 시간에 대한 제약이 없고, 환불 승인자의 OTP 코드가 필요하다는 점입니다.
        """
        serializer = OrderTotalRefundSerializer(
            instance=self.get_object(),
            data={"totp": request.GET.get("otp")},
            context={"check_refundable_date": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)
