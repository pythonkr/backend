import typing

from core.const.tag import OpenAPITag
from django.db.models import Exists, OuterRef, QuerySet
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import ErrorResponse403Serializer, ValidationErrorResponseSerializer
from rest_framework import mixins, request, response, status, viewsets
from shop.order.models import Order, OrderProductRelation
from shop.order.serializers.dto import OrderDto
from shop.payment_history.models import PaymentHistory
from shop.serializers.cart_validation import ProductOrderableCheckSerializer
from user.models import UserExt


@extend_schema_view(
    list=extend_schema(
        summary="장바구니 정보 조회",
        tags=[OpenAPITag.SHOP_CART],
        responses={
            status.HTTP_200_OK: OrderDto,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
)
class CartViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderDto

    def get_queryset(self) -> QuerySet[Order]:
        if not isinstance(self.request.user, UserExt):
            return Order.objects.none()

        return (
            Order.objects.filter_has_no_payment_histories()
            .with_dto_prefetches()
            .filter(user=self.request.user)
            .distinct()
        )

    def list(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        # 사용자 당 장바구니는 하나만 존재하므로, 장바구니가 여러 개일 경우 가장 최근에 생성된 장바구니를 가져옵니다.
        if cart := self.get_queryset().first():
            return response.Response(data=self.get_serializer(cart).data)
        return response.Response(data={})


@extend_schema_view(
    create=extend_schema(
        summary="장바구니에 상품 추가",
        tags=[OpenAPITag.SHOP_CART],
        responses={
            status.HTTP_201_CREATED: ProductOrderableCheckSerializer(many=True),
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
    destroy=extend_schema(
        summary="장바구니에서 상품 제거",
        tags=[OpenAPITag.SHOP_CART],
        parameters=[
            OpenApiParameter(
                name="order_product_rel_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
)
class CartProductViewSet(mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    lookup_url_kwarg = "order_product_rel_id"
    serializer_class = ProductOrderableCheckSerializer

    def get_queryset(self) -> QuerySet[Order]:
        if not isinstance(self.request.user, UserExt):
            return OrderProductRelation.objects.none()

        return OrderProductRelation.objects.filter_active().filter(
            ~Exists(PaymentHistory.objects.filter_active().filter(order=OuterRef("order"))),
            order__deleted_at__isnull=True,
            order__user=self.request.user,
            # 숨겨진 상품(추가 후원, 배송비 등)은 별도의 API를 통해서만 추가/삭제가 가능합니다.
            product__hidden=False,
            single_product_cart__isnull=True,
            status=OrderProductRelation.OrderProductStatus.pending,
        )
