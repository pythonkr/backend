import functools

from core.const.shop_error_messages import PortOneWebhookFailureMessages
from core.external_apis.portone.client import PortOneException, PortOneExceptionGroup, portone_client
from django.db import models, transaction
from rest_framework import serializers
from shop.order.models import Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus, is_legal_payment_status_transition
from shop.payment_history.tasks import send_payment_completed_notifications


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
        if order := Order.objects.filter_active().filter(id=obj_id).first():
            return order
        if cart := SingleProductCart.objects.filter_active().filter(id=obj_id).first():
            return cart
        return None

    def validate_status(self, value: str) -> str:
        if value == PortOneV1WebhookRequestStatus.READY:
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.VIRTUAL_ACCOUNT_NOT_SUPPORTED, code="unsupported"
            )
        elif value == PortOneV1WebhookRequestStatus.FAILED:
            raise serializers.ValidationError(detail=PortOneWebhookFailureMessages.PURCHASE_FAILED, code="forgery")
        elif value == PortOneV1WebhookRequestStatus.CANCELLED:
            # TODO: 관리자 콘솔 취소 자동 처리는 미구현 — 우선 거부하고 운영자가 수동으로 환불 처리.
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.CANCELLED_NOT_SUPPORTED, code="unsupported"
            )
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

        if retrieved_order_data["status"] != PortOneV1PaymentStatus.PAID:
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.UNEXPECTED_RETRIEVED_ORDER_STATUS, code="forgery"
            )

        if retrieved_order_data["currency"] != "KRW":
            raise serializers.ValidationError(detail=PortOneWebhookFailureMessages.UNSUPPORTED_CURRENCY, code="forgery")

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

    @transaction.atomic
    def create(self, validated_data: dict) -> PaymentHistory:
        # CANCELLED webhook (관리자 콘솔 취소) 자동 처리는 미구현 — validate_status 에서 거부됨.
        payment_info = PortOneV1PaymentDetailSerializer(instance=self.portone_payment_info).data
        order = self._lock_or_promote_order(validated_data["merchant_uid"])

        # State machine — webhook retry 등 중복/불법 전이는 거부.
        next_status = PaymentHistoryStatus.completed
        if not is_legal_payment_status_transition(order.current_status, next_status):
            raise serializers.ValidationError(
                detail=PortOneWebhookFailureMessages.ILLEGAL_STATUS_TRANSITION, code="illegal_transition"
            )

        for product_rel in order.products.all():
            product_rel.status = OrderProductRelation.OrderProductStatus.paid
            product_rel.save()

        payment_history = PaymentHistory.objects.create(
            order=order,
            imp_id=validated_data["imp_uid"],
            status=next_status,
            price=payment_info["amount"],
        )

        # 결제 완료 알림(알림톡 + 이메일)을 트랜잭션 커밋 후 비동기로 발송.

        transaction.on_commit(lambda: send_payment_completed_notifications.delay(str(order.id)))

        return payment_history

    @staticmethod
    def _lock_or_promote_order(obj_id: str) -> Order:
        """Order 가 있으면 lock 하여 반환. SingleProductCart 만 있으면 lock + to_order() 로 승격.

        모델 관계: `SingleProductCart` 는 단일 상품 장바구니의 결제 전 임시 상태이고,
        결제가 성공하면 `to_order()` 로 같은 PK 의 `Order` 로 승격되며 cart 자체는 hard delete 된다.
        webhook 은 `merchant_uid` (= cart/order PK) 로 호출되므로, 같은 PK 의 두 모델 중 현재 살아있는 쪽을 lock 한다.

        동시 webhook race 시: 첫 호출이 cart lock + to_order() commit 후, 두 번째 호출은
        cart 가 hard_delete 된 상태로 lock 해제됨 → Order 재조회에서 승격된 Order 발견.
        """
        if order := Order.objects.select_for_update().filter_active().filter(id=obj_id).first():
            return order
        if cart := SingleProductCart.objects.select_for_update().filter_active().filter(id=obj_id).first():
            return cart.to_order()
        # 첫 lock 시 cart 가 다른 webhook 에 의해 promote 된 경우 — Order 재조회.
        if order := Order.objects.select_for_update().filter_active().filter(id=obj_id).first():
            return order
        raise serializers.ValidationError(detail=PortOneWebhookFailureMessages.ORDER_NOT_FOUND, code="forgery")


class PortOneV1WebhookResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="success", read_only=True)
    message = serializers.CharField(default="일반 결제 성공", read_only=True)
