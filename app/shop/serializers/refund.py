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


def _check_totp(context: dict, totp_value: str | None) -> None:
    if not context.get("check_totp", True):
        return
    totp = totp_value or ""
    if not totp:
        raise serializers.ValidationError({"totp": [PermissionErrorMessages.OTP_REQUIRED]})
    if not (totp.isdigit() and TOTPInfo(key=settings.SHOP.refund_authorizer_secret_key.encode()).check(totp)):
        raise serializers.ValidationError({"totp": [PermissionErrorMessages.INVALID_OTP_CODE]})


class OrderTotalRefundSerializerAttributeType(typing.TypedDict):
    id: str | uuid.UUID
    totp: typing.NotRequired[str]


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

    Context:
    - check_refundable_date (default True): 환불 가능 일자를 지난 상품이 있어도 환불 허용 시 False.
    - check_totp (default True): TOTP 검증 강제 여부. False 시 totp 입력 무시.
    """

    totp = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)

    class Meta:
        model = Order
        fields = ("id", "totp")

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

    def validate(self, attrs: OrderTotalRefundSerializerAttributeType) -> OrderTotalRefundSerializerAttributeType:
        _check_totp(self.context, attrs.get("totp"))

        check_refundable_date = self.context.get("check_refundable_date", True)
        order: Order = typing.cast(Order, self.instance)
        if reason := order.not_fully_refundable_reason:
            if not (
                reason == NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date
            ):
                raise serializers.ValidationError(reason)

        return attrs

    @transaction.atomic
    def refund(self) -> None:
        # Order 를 aggregate root 로 lock — 동일 Order 의 동시 refund (total/partial) 직렬화.
        self.instance = Order.objects.select_for_update().get(id=typing.cast(Order, self.instance).id)
        for attr in ("refund_target_prod_rels", "expected_refund_price"):
            self.__dict__.pop(attr, None)

        # validate() 가 lock 전 stale 상태를 봤을 수 있어 lock 후 invariant 재검사.
        order = typing.cast(Order, self.instance)
        if reason := order.not_fully_refundable_reason:
            check_refundable_date = self.context.get("check_refundable_date", True)
            if not (
                reason == NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date
            ):
                raise serializers.ValidationError(reason)

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
    totp: typing.NotRequired[str]


class OrderProductRefundSerializer(serializers.ModelSerializer):
    """
    주문에서 특정 상품에 대한 부분 환불을 진행합니다.
    아래의 경우에는 ValidationError를 발생시킵니다.
    - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
    - 이미 사용했거나 결제 전, 환불된 상품인 경우
    - 환불 가능한 일자를 지난 상품이 있는 경우
    - 환불 금액이 없는 경우

    Context:
    - check_refundable_date (default True): 환불 가능 일자를 지난 상품이어도 환불 허용 시 False.
    - check_totp (default True): TOTP 검증 강제 여부. False 시 totp 입력 무시.
    """

    totp = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)

    class Meta:
        model = OrderProductRelation
        fields = ("id", "totp")

    @functools.cached_property
    def product(self) -> Product:
        return typing.cast(OrderProductRelation, self.instance).product

    def validate(self, attrs: OrderProductRefundSerializerAttributeType) -> OrderProductRefundSerializerAttributeType:
        _check_totp(self.context, attrs.get("totp"))

        check_refundable_date = self.context.get("check_refundable_date", True)
        order_product_rel = typing.cast(OrderProductRelation, self.instance)

        if reason := order_product_rel.not_refundable_reason:
            if not (reason == NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date):
                raise serializers.ValidationError(reason)

        return attrs

    @transaction.atomic
    def refund(self) -> None:
        order_product_rel = typing.cast(OrderProductRelation, self.instance)
        # 부모 Order 를 aggregate root 로 lock — 같은 Order 의 동시 refund 직렬화.
        order = Order.objects.select_for_update().get(id=order_product_rel.order_id)
        order_product_rel.refresh_from_db()

        # validate() 가 lock 전 stale 상태를 봤을 수 있어 lock 후 invariant 재검사.
        if reason := order_product_rel.not_refundable_reason:
            check_refundable_date = self.context.get("check_refundable_date", True)
            if not (reason == NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED and not check_refundable_date):
                raise serializers.ValidationError(reason)

        refund_request_price = order_product_rel.price + order_product_rel.donation_price
        before_leftover_price = order.current_paid_price
        after_leftover_price = before_leftover_price - refund_request_price

        portone_client.req_cancel_payment(
            merchant_id=str(order.id),
            refund_request_price=refund_request_price,
            current_leftover_price=before_leftover_price,
        )

        order_product_rel.status = OrderProductRelation.OrderProductStatus.refunded
        order_product_rel.save()

        active_statuses = (OrderProductRelation.OrderProductStatus.paid, OrderProductRelation.OrderProductStatus.used)
        next_status = (
            PaymentHistoryStatus.partial_refunded
            if OrderProductRelation.objects.filter(order_id=order.id, status__in=active_statuses).exists()
            else PaymentHistoryStatus.refunded
        )
        imp_id = order.latest_imp_id
        PaymentHistory.objects.create(order=order, imp_id=imp_id, status=next_status, price=after_leftover_price)
