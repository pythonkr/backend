import datetime
import functools
import typing
import uuid

from core.const.shop_error_messages import NotRefundableErrorMessages, PermissionErrorMessages
from core.external_apis.portone.client import portone_client
from core.util.totp import TOTPInfo
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Product


class OrderTotalRefundSerializerAttributeType(typing.TypedDict):
    id: str | uuid.UUID
    totp: typing.NotRequired[str]
    check_refundable_date: typing.NotRequired[bool]


class OrderTotalRefundSerializer(serializers.ModelSerializer):
    """
    Order의 사용 및 환불하지 않은 상품을 refunded 상태로 변경하고, 결제 취소를 요청합니다.
    아래의 경우에는 ValidationError를 발생시킵니다.
    - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
    - 이미 사용한 상품이 있는 경우
    - 환불할 상품이 없는 경우
    - 환불할 금액이 없는 경우
    - 환불할 금액이 음수인 경우
    - 환불할 금액이 남은 결제 금액과 일치하지 않는 경우
    - 환불 가능한 일자를 지난 상품이 있는 경우
    """

    totp = serializers.CharField(required=False, allow_blank=False, allow_null=False, write_only=True)
    check_refundable_date = serializers.BooleanField(default=True, write_only=True)

    class Meta:
        model = Order
        fields = ("id", "totp", "check_refundable_date")

    @functools.cached_property
    def refund_target_prod_rels(self) -> list[OrderProductRelation]:
        return list(
            typing.cast(Order, self.instance).products.filter(status=OrderProductRelation.OrderProductStatus.paid)
        )

    @functools.cached_property
    def expected_refund_price(self) -> int:
        if not self.refund_target_prod_rels:
            return 0
        return sum(prod.price + prod.donation_price for prod in self.refund_target_prod_rels)

    def validate_totp(self, value: str) -> str:
        if not (value.isdigit() and TOTPInfo(key=settings.SHOP.refund_authorizer_secret_key.encode()).check(value)):
            raise serializers.ValidationError(PermissionErrorMessages.INVALID_OTP_CODE)
        return value

    def validate_check_refundable_date(self, value: bool) -> bool:
        now = datetime.datetime.now().astimezone()
        if value and any(rel.product.refundable_ends_at < now for rel in self.refund_target_prod_rels):
            raise serializers.ValidationError(NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED)

        return value

    def validate(self, attrs: OrderTotalRefundSerializerAttributeType) -> OrderTotalRefundSerializerAttributeType:
        check_refundable_date: bool = attrs.get("check_refundable_date", True)
        order: Order = typing.cast(Order, self.instance)

        if reason := order.not_fully_refundable_reason:
            if reason == NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date:
                pass
            else:
                raise serializers.ValidationError(reason)

        return attrs

    @transaction.atomic
    def refund(self) -> None:
        order = typing.cast(Order, self.instance)

        portone_client.req_cancel_payment(
            merchant_id=str(order.id),
            refund_request_price=self.expected_refund_price,
            current_leftover_price=self.expected_refund_price,
        )

        for rel in self.refund_target_prod_rels:
            rel.status = OrderProductRelation.OrderProductStatus.refunded
            rel.save()

        PaymentHistory.objects.create(
            order=order,
            imp_id=order.current_payment_history.imp_id,
            status=PaymentHistoryStatus.refunded,
            price=0,
        )


class OrderProductRefundSerializerAttributeType(typing.TypedDict):
    id: str | uuid.UUID
    check_refundable_date: typing.NotRequired[bool]


class OrderProductRefundSerializer(serializers.ModelSerializer):
    """
    주문에서 특정 상품에 대한 부분 환불을 진행합니다.
    아래의 경우에는 ValidationError를 발생시킵니다.
    - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
    - 이미 사용했거나 결제 전, 환불된 상품인 경우
    - 환불 가능한 일자를 지난 상품이 있는 경우
    - 환불 금액이 없는 경우
    """

    check_refundable_date = serializers.BooleanField(default=True, write_only=True)

    class Meta:
        model = OrderProductRelation
        fields = ("id", "check_refundable_date")

    @functools.cached_property
    def product(self) -> Product:
        return typing.cast(OrderProductRelation, self.instance).product

    def validate(self, attrs: OrderProductRefundSerializerAttributeType) -> OrderProductRefundSerializerAttributeType:
        check_refundable_date: bool = attrs.get("check_refundable_date", True)
        order_product_rel = typing.cast(OrderProductRelation, self.instance)

        if reason := order_product_rel.not_refundable_reason:
            if reason == NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date:
                pass
            else:
                raise serializers.ValidationError(reason)

        return attrs

    @transaction.atomic
    def refund(self) -> None:
        order_product_rel = typing.cast(OrderProductRelation, self.instance)
        order = typing.cast(Order, order_product_rel.order)

        refund_request_price = order_product_rel.price + order_product_rel.donation_price
        before_leftover_price = order_product_rel.order.current_paid_price
        after_leftover_price = before_leftover_price - refund_request_price

        portone_client.req_cancel_payment(
            merchant_id=str(order.id),
            refund_request_price=refund_request_price,
            current_leftover_price=before_leftover_price,
        )

        refund_status = OrderProductRelation.OrderProductStatus.refunded
        order_product_rel.status = refund_status
        order_product_rel.save()

        next_status = (
            PaymentHistoryStatus.partial_refunded
            if OrderProductRelation.objects.filter(order_id=order.id).exclude(status=refund_status).exists()
            else PaymentHistoryStatus.refunded
        )
        imp_id = order.latest_imp_id
        PaymentHistory.objects.create(order=order, imp_id=imp_id, status=next_status, price=after_leftover_price)
