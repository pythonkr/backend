import typing

from core.const.regex import UUID_V4_PATTERN
from core.const.shop_error_messages import CartNotOrderableErrorMessages
from core.const.tag import OpenAPITag
from core.external_apis.portone.client import PortOneException, portone_client
from core.openapi.schemas import build_html_responses
from django.conf import settings
from django.db import models, transaction
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import ErrorResponse403Serializer, ValidationErrorResponseSerializer
from rest_framework import mixins, renderers, request, response, serializers, status, viewsets
from rest_framework.decorators import action
from shop.order.models import CustomerInfo, Order, OrderProductRelation, OrderQuerySet
from shop.order.serializers.dto import OrderDto, SingleProductCartDto
from shop.order.serializers.validator import (
    OptionProductOptionCustomResponseModifyRequestSerializer,
    OrderProductUpdateSerializer,
)
from shop.payment_history.models import PaymentHistory
from shop.serializers.cart_validation import (
    CartOrderableCheckSerializer,
    CustomerInfoCheckSerializer,
    OrderableCheckSerializerMode,
    ProductOrderableCheckSerializer,
    SingleProductCartOrderableCheckSerializer,
)
from shop.serializers.refund import OrderProductRefundSerializer, OrderTotalRefundSerializer
from user.models import UserExt


@extend_schema_view(
    list=extend_schema(
        summary="주문 이력 목록 조회",
        tags=[OpenAPITag.SHOP_ORDER],
        responses={
            status.HTTP_200_OK: OrderDto(many=True),
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
    retrieve=extend_schema(
        summary="주문 이력 상세 조회",
        tags=[OpenAPITag.SHOP_ORDER],
        parameters=[
            OpenApiParameter(
                name="order_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            status.HTTP_200_OK: OrderDto,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
)
class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    lookup_url_kwarg = "order_id"
    lookup_value_regex = UUID_V4_PATTERN
    serializer_class = OrderDto
    queryset = Order.objects.select_related("customer_info")

    def get_queryset(self) -> models.QuerySet[Order]:
        base_qs = typing.cast(OrderQuerySet, self.queryset)

        if not isinstance(self.request.user, UserExt):
            return Order.objects.none()

        if self.action == "create":
            # Cart -> Order로 전환 시에는 payment_histories가 없는 Order만 가져와야 합니다.
            return base_qs.filter_has_no_payment_histories().filter(user=self.request.user).distinct()
        if self.action == "retrieve_receipt":
            user_filter = {} if self.request.user.is_staff else {"user": self.request.user}
            return base_qs.filter_has_payment_histories().filter(**user_filter).distinct()
        return base_qs.with_dto_prefetches().filter_has_payment_histories().filter(user=self.request.user).distinct()

    @extend_schema(
        summary="단건 주문 프로세스 시작",
        tags=[OpenAPITag.SHOP_ORDER],
        request=SingleProductCartOrderableCheckSerializer,
        responses={
            status.HTTP_201_CREATED: SingleProductCartDto,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    )
    @action(detail=False, methods=["POST"], url_path="single")
    def create_single_product_order(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """단일 상품 주문을 생성합니다."""
        context = self.get_serializer_context() | {"mode": OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT}
        serializer = SingleProductCartOrderableCheckSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        order_product_rel: OrderProductRelation = serializer.save()

        assert order_product_rel.single_product_cart  # nosec: B101
        cart = order_product_rel.single_product_cart
        cart.prepare_payment()

        portone_client.register_or_update_prepared_payment(merchant_id=cart.merchant_uid, price=cart.prepared_price)

        return response.Response(data=SingleProductCartDto(instance=cart).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="주문 프로세스 시작",
        tags=[OpenAPITag.SHOP_ORDER],
        request=CustomerInfoCheckSerializer,
        responses={
            status.HTTP_201_CREATED: OrderDto,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    )
    @transaction.atomic
    def create(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """아직 결제하지 않은 Order(Cart)를 가져온 후, PortOne에 결제 금액 사전 등록을 하고, Order 데이터를 응답합니다."""
        if not ((cart := self.get_queryset().first()) and cart.products.filter_active().exists()):
            raise serializers.ValidationError(CartNotOrderableErrorMessages.EMPTY)

        customer_info = CustomerInfo.objects.filter_active().filter(order=cart).first()
        customer_info_serializer = CustomerInfoCheckSerializer(instance=customer_info, data=request.data)
        customer_info_serializer.is_valid(raise_exception=True)
        customer_info_serializer.save(order=cart)

        context = self.get_serializer_context() | {"mode": OrderableCheckSerializerMode.CHECKOUT_CART}
        cart_product_rels = sorted(cart.products.filter_active(), key=lambda x: x.price, reverse=True)
        ProductOrderableCheckSerializer(
            data=[
                {
                    "product": product_rel.product_id,
                    "options": [
                        {
                            "product_option_group": product_option_rel.product_option_group_id,
                            "product_option": product_option_rel.product_option_id,
                            "custom_response": product_option_rel.custom_response,
                        }
                        for product_option_rel in product_rel.options.filter_active()
                    ],
                }
                for product_rel in cart_product_rels
            ],
            context=context,
            many=True,
        ).is_valid(raise_exception=True)
        CartOrderableCheckSerializer(data={"cart": cart.id}, context=context).is_valid(raise_exception=True)

        cart.name = cart_product_rels[0].product.name
        cart.name_ko = cart_product_rels[0].product.name_ko
        cart.name_en = cart_product_rels[0].product.name_en
        if len(cart_product_rels) > 1:
            cart.name += f" 외 {len(cart_product_rels) - 1}개"
            cart.name_ko += f" 외 {len(cart_product_rels) - 1}개"
            cart.name_en += f" and {len(cart_product_rels) - 1} more"
        cart.save()
        cart.prepare_payment()

        # idempotent + forward-only — DB commit 후 비동기 호출. 실패 시 클라이언트 retry 가 자연 보상.
        transaction.on_commit(
            lambda: portone_client.register_or_update_prepared_payment(
                merchant_id=cart.merchant_uid, price=cart.prepared_price
            )
        )

        dto_cart = Order.objects.for_dto_response().get(id=cart.id)
        return response.Response(data=OrderDto(instance=dto_cart).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="해당 주문에 남아있는 환불 가능한 모든 상품 환불 (주문 전체 환불)",
        tags=[OpenAPITag.SHOP_ORDER_REFUND],
        parameters=[
            OpenApiParameter(
                name="order_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    )
    @transaction.atomic
    def destroy(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """Order의 사용 및 환불하지 않은 상품을 refunded 상태로 변경하고, 결제 취소를 요청합니다."""
        serializer = OrderTotalRefundSerializer(instance=self.get_object(), data={}, context={"check_totp": False})
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="NHN KCP 영수증 페이지",
        tags=[OpenAPITag.SHOP_ORDER],
        responses=(
            build_html_responses(names=["NHN KCP의 영수증 페이지로 redirect하는 HTML"], status_code=status.HTTP_200_OK)
            | build_html_responses(names=["주문을 찾을 수 없는 경우"], status_code=status.HTTP_404_NOT_FOUND)
        ),
    )
    @action(detail=True, methods=["GET"], url_path="receipt", renderer_classes=[renderers.TemplateHTMLRenderer])
    def retrieve_receipt(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """NHN KCP의 영수증 페이지로 redirect하는 HTML을 응답합니다."""
        order: Order = self.get_object()
        if not order.latest_imp_id:
            return response.Response(
                data={"error_msg": "본 주문은 영수증을 조회할 수 없습니다.\n파이콘 준비 위원회에 문의해주세요."},
                status=status.HTTP_404_NOT_FOUND,
                template_name="scancode_error.html",
            )

        try:
            receipt_serializer = portone_client.get_kcp_receipt_search_data(imp_uid=order.latest_imp_id)
        except PortOneException:
            return response.Response(
                data={
                    "error_msg": "지금은 영수증을 조회할 수 없습니다, 잠시 후 다시 시도해주세요.\n문제가 지속되면 파이콘 준비 위원회에 문의 부탁드립니다."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                template_name="scancode_error.html",
            )

        return response.Response(
            template_name="receipt_kcp.html",
            data={
                "search_data": receipt_serializer.to_search_data(),
                "sign_data": receipt_serializer.to_kcp_signed_search_data(
                    private_key=settings.NHN_KCP.pg_api_private_key,
                    password=settings.NHN_KCP.pg_api_password,
                ),
                "cert_info": settings.NHN_KCP.pg_api_cert,
            },
        )


@extend_schema_view(
    partial_update=extend_schema(
        summary="주문 상품 수정 (옵션 답변 / 티켓 참가자 정보)",
        tags=[OpenAPITag.SHOP_ORDER],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    ),
)
class OrderProductViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    lookup_url_kwarg = "order_product_rel_id"
    serializer_class = OrderProductUpdateSerializer
    http_method_names = ["patch", "delete", "head", "options"]

    def get_queryset(self) -> models.QuerySet[OrderProductRelation]:
        if not isinstance(self.request.user, UserExt):
            return OrderProductRelation.objects.none()

        return (
            OrderProductRelation.objects.filter_active()
            .filter(
                models.Exists(PaymentHistory.objects.filter_active().filter(order=models.OuterRef("order"))),
                order_id=self.kwargs["order_id"],
                order__deleted_at__isnull=True,
                order__user=self.request.user,
                single_product_cart__isnull=True,
                status=OrderProductRelation.OrderProductStatus.paid,
            )
            .distinct()
        )

    def update(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        super().update(request, *args, **kwargs)
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="주문 중 특정 상품의 옵션 수정",
        deprecated=True,
        tags=[OpenAPITag.SHOP_ORDER],
        request=OptionProductOptionCustomResponseModifyRequestSerializer(many=True),
        responses={
            status.HTTP_200_OK: OrderDto,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    )
    @action(detail=True, methods=["PATCH"], url_path="options")
    @transaction.atomic
    def modify_options(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        order_product_rel: OrderProductRelation = self.get_object()
        for datum in request.data:
            serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
                data=datum,
                context={"order_product_rel": order_product_rel},
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        dto_order = Order.objects.for_dto_response().get(id=order_product_rel.order_id)
        return response.Response(data=OrderDto(instance=dto_order).data)

    @extend_schema(
        summary="주문의 특정 상품 환불 (주문 부분 환불)",
        tags=[OpenAPITag.SHOP_ORDER_REFUND],
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
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: ErrorResponse403Serializer,
        },
    )
    @transaction.atomic
    def destroy(
        self, request: request.Request, *args: tuple[typing.Any], **kwargs: dict[str, typing.Any]
    ) -> response.Response:
        """부분 환불을 진행합니다."""
        serializer = OrderProductRefundSerializer(instance=self.get_object(), data={}, context={"check_totp": False})
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)
