import functools

from core.const.shop_error_messages import PortOneWebhookFailureMessages
from core.external_apis.portone.client import PortOneException, PortOneExceptionGroup, portone_client
from django.db import models
from rest_framework import serializers
from shop.order.models import Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus


class PortOneV1PaymentStatus(models.TextChoices):
    READY = "ready", "미결제"
    PAID = "paid", "결제완료"
    CANCELLED = "cancelled", "결제취소"
    FAILED = "failed", "결제실패"


class PortOneV1PaymentCancelHistorySerializer(serializers.Serializer):
    pg_tid = serializers.CharField(required=True, allow_blank=False, allow_null=False, help_text="PG사 승인 취소 번호")
    cancellation_id = serializers.CharField(required=True, help_text="결제 취소 ID")

    amount = serializers.FloatField(required=True, help_text="결제 취소 금액")

    cancelled_at = serializers.IntegerField(required=True, help_text="결제 취소 시각(UNIX timestamp)")
    reason = serializers.CharField(required=True, help_text="취소 사유")


class PortOneV1PaymentDetailSerializer(serializers.Serializer):
    imp_uid = serializers.CharField(required=True, allow_blank=False, allow_null=False, help_text="포트원 거래고유번호")
    merchant_uid = serializers.CharField(
        required=True, allow_blank=False, allow_null=False, help_text="가맹점 주문번호"
    )

    amount = serializers.FloatField(required=True, help_text="결제 금액")
    cancel_amount = serializers.FloatField(required=True, help_text="결제건의 누적 취소 금액")
    currency = serializers.CharField(required=True, help_text="결제통화 구분코드")

    status = serializers.ChoiceField(choices=PortOneV1PaymentStatus.choices, required=True, help_text="결제 상태")

    started_at = serializers.IntegerField(required=False, help_text="결제 요청 시각(UNIX timestamp)")
    paid_at = serializers.IntegerField(required=False, help_text="결제 성공 시각(UNIX timestamp)")
    failed_at = serializers.IntegerField(required=False, help_text="결제 실패 시각(UNIX timestamp)")
    cancelled_at = serializers.IntegerField(required=False, help_text="결제 취소 시각(UNIX timestamp)")
    fail_reason = serializers.CharField(required=False, allow_null=True, help_text="결제실패 사유")

    cancel_history = PortOneV1PaymentCancelHistorySerializer(many=True, required=False, help_text="결제취소 이력")


class PortOneV1WebhookRequestStatus(models.TextChoices):
    PAID = "paid", "결제 승인"
    READY = "ready", "가상 계좌 발급 완료"
    FAILED = "failed", "결제 실패"
    CANCELLED = "cancelled", "관리자 콘솔에서 결제 취소"


class PortOneV1WebhookRequestSerializer(serializers.Serializer):
    imp_uid = serializers.CharField(required=True, help_text="PortOne 결제 고유번호")
    merchant_uid = serializers.CharField(required=True, help_text="Order or SingleProductCart ID")
    status = serializers.ChoiceField(
        choices=PortOneV1WebhookRequestStatus.choices,
        required=True,
        help_text="결제 결과",
    )
    cancellation_id = serializers.CharField(required=False, help_text="취소내역 ID")

    @functools.cached_property
    def portone_payment_info(self) -> dict:
        return portone_client.find_payment_info(self.initial_data["imp_uid"])

    @functools.cached_property
    def cart_or_order(self) -> Order | SingleProductCart | None:
        obj_id: str = self.initial_data["merchant_uid"]
        if order := Order.objects.filter(id=obj_id).first():
            return order
        if cart := SingleProductCart.objects.filter(id=obj_id).first():
            return cart
        return None

    def validate_status(self, value: str) -> str:
        if value == PortOneV1WebhookRequestStatus.READY:
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.VIRTUAL_ACCOUNT_NOT_SUPPORTED, code="unsupported"
            )
        elif value == PortOneV1WebhookRequestStatus.FAILED:
            raise serializers.ValidationError(detail=PortOneWebhookFailureMessages.PURCHASE_FAILED, code="forgery")
        return value

    def validate(self, data: dict) -> dict:
        order: Order | SingleProductCart | None = self.cart_or_order

        if not order:
            raise serializers.ValidationError(detail=PortOneWebhookFailureMessages.ORDER_NOT_FOUND, code="forgery")

        try:
            payment_serializer = PortOneV1PaymentDetailSerializer(data=self.portone_payment_info)
            payment_serializer.is_valid(raise_exception=True)
            retrieved_order_data = payment_serializer.validated_data
        except (PortOneException, PortOneExceptionGroup) as e:
            raise serializers.ValidationError(detail=str(e), code="portone_error") from e

        if retrieved_order_data["status"] not in (PortOneV1PaymentStatus.PAID, PortOneV1PaymentStatus.CANCELLED):
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.UNEXPECTED_RETRIEVED_ORDER_STATUS, code="forgery"
            )

        if retrieved_order_data["merchant_uid"] != str(order.id):
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.UNEXPECTED_RETRIEVED_ORDER_ID, code="forgery"
            )

        if (
            data["status"] == PortOneV1WebhookRequestStatus.PAID
            and order.first_paid_price != retrieved_order_data["amount"]
        ):
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.UNEXPECTED_PAID_PRICE, code="forgery"
            )

        return data

    def create(self, validated_data: dict) -> PaymentHistory:
        # TODO: 결제 취소 (payment_serializer.validated_data["status"] == PortOneV1PaymentStatus.CANCELLED)인 경우,
        #       cancellation_id를 확인하고 환불 내역을 저장하는 로직을 추가해야 합니다.
        payment_info = PortOneV1PaymentDetailSerializer(instance=self.portone_payment_info).data

        assert (order_or_cart := self.cart_or_order)  # nosec: B101
        order = order_or_cart.to_order() if isinstance(order_or_cart, SingleProductCart) else order_or_cart

        for product_rel in order.products.all():
            product_rel.status = OrderProductRelation.OrderProductStatus.paid
            product_rel.save()

        return PaymentHistory.objects.create(
            order=order,
            imp_id=validated_data["imp_uid"],
            status=PaymentHistoryStatus.completed,
            price=payment_info["amount"],
        )


class PortOneV1WebhookResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="success", read_only=True)
    message = serializers.CharField(default="일반 결제 성공", read_only=True)
