from functools import cached_property
from traceback import format_exception
from typing import NoReturn, cast

from core.const.shop_error_messages import PortOneWebhookFailureCode
from core.external_apis.portone.client import PortOneException, PortOneExceptionGroup, portone_client
from core.util.dateutil import now_aware
from django.db import models, transaction
from rest_framework import serializers
from shop.order.models import Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import (
    PaymentHistory,
    PaymentHistoryStatus,
    PaymentWebhookEvent,
    is_legal_payment_status_transition,
)
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

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._queued_webhook_events: list[dict[str, object]] = []

    def is_valid(self, *, raise_exception: bool = False) -> bool:
        try:
            return super().is_valid(raise_exception=raise_exception)
        finally:
            PaymentWebhookEvent.objects.bulk_create([PaymentWebhookEvent(**e) for e in self._queued_webhook_events])
            self._queued_webhook_events.clear()

    def save(self, **kwargs: object) -> PaymentHistory:
        try:
            return super().save(**kwargs)
        finally:
            PaymentWebhookEvent.objects.bulk_create([PaymentWebhookEvent(**e) for e in self._queued_webhook_events])
            self._queued_webhook_events.clear()

    def validate_status(self, value: str) -> str:
        if value == PortOneV1WebhookRequestStatus.READY:
            self._reject(PortOneWebhookFailureCode.VIRTUAL_ACCOUNT_NOT_SUPPORTED)
        elif value == PortOneV1WebhookRequestStatus.FAILED:
            self._reject(PortOneWebhookFailureCode.PURCHASE_FAILED)
        elif value == PortOneV1WebhookRequestStatus.CANCELLED:
            # TODO: 관리자 콘솔 취소 자동 처리는 미구현 — 우선 거부하고 운영자가 수동으로 환불 처리.
            self._reject(PortOneWebhookFailureCode.CANCELLED_NOT_SUPPORTED)
        return value

    def validate(self, data: dict) -> dict:
        if not (order := cast(Order | SingleProductCart | None, self.cart_or_order)):
            self._reject(PortOneWebhookFailureCode.ORDER_NOT_FOUND)

        try:
            payment_info = self.portone_payment_info
        except (PortOneException, PortOneExceptionGroup) as e:
            self._queue_event(PaymentWebhookEvent.EventType.PAYMENT_LOOKUP_FAILED, exc=e)
            raise serializers.ValidationError(detail=str(e), code="portone_error") from e
        self._queue_event(PaymentWebhookEvent.EventType.PAYMENT_LOOKUP_SUCCEEDED)

        payment_serializer = PortOneV1PaymentDetailSerializer(data=payment_info)
        payment_serializer.is_valid(raise_exception=True)
        retrieved_order_data = payment_serializer.validated_data

        if retrieved_order_data["status"] != PortOneV1PaymentStatus.PAID:
            self._reject(PortOneWebhookFailureCode.UNEXPECTED_RETRIEVED_ORDER_STATUS)

        if retrieved_order_data["merchant_uid"] != data["merchant_uid"]:
            self._reject(PortOneWebhookFailureCode.UNEXPECTED_RETRIEVED_ORDER_ID)

        if retrieved_order_data["currency"] != "KRW":
            self._reject_and_cancel_paid_payment(PortOneWebhookFailureCode.UNSUPPORTED_CURRENCY)

        if not order.matches_payment_preparation(data["merchant_uid"], retrieved_order_data["amount"]):
            self._reject_and_cancel_paid_payment(PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE)

        return data

    @transaction.atomic
    def create(self, validated_data: dict) -> PaymentHistory:
        # CANCELLED webhook (관리자 콘솔 취소) 자동 처리는 미구현 — validate_status 에서 거부됨.
        order = self._lock_or_promote_order(validated_data["merchant_uid"])
        # cart→Order 승격 시 cached cart_or_order 가 stale (cart 는 hard_delete 됨) — 새 Order 로 교체해
        # 이후 _queue_event 가 derive 하는 order/single_product_cart 가 deleted row 를 가리키지 않게 한다.
        self.__dict__["cart_or_order"] = order
        if not order.matches_payment_preparation(validated_data["merchant_uid"], self.portone_payment_info["amount"]):
            self._reject_and_cancel_paid_payment(PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE)

        # State machine — webhook retry 등 중복/불법 전이는 거부.
        next_status = PaymentHistoryStatus.completed
        if not is_legal_payment_status_transition(order.current_status, next_status):
            self._reject(PortOneWebhookFailureCode.ILLEGAL_STATUS_TRANSITION)

        for product_rel in order.products.filter_active():
            product_rel.status = OrderProductRelation.OrderProductStatus.paid
            product_rel.save()

        payment_history = PaymentHistory.objects.create(
            order=order,
            imp_id=validated_data["imp_uid"],
            status=next_status,
            price=self.portone_payment_info["amount"],
        )
        self._queue_event(PaymentWebhookEvent.EventType.PAYMENT_ACCEPTED, payment_history=payment_history)

        # 결제 완료 알림(알림톡 + 이메일)을 트랜잭션 커밋 후 비동기로 발송.
        transaction.on_commit(lambda: send_payment_completed_notifications.delay(str(order.id)))

        return payment_history

    @cached_property
    def portone_payment_info(self) -> dict:
        return portone_client.find_payment_info(self.initial_data["imp_uid"])

    @cached_property
    def cart_or_order(self) -> Order | SingleProductCart | None:
        merchant_uid = self.initial_data.get("merchant_uid")
        if order := Order.objects.filter_by_merchant_uid(merchant_uid).first():
            return order
        if cart := SingleProductCart.objects.filter_by_merchant_uid(merchant_uid).first():
            return cart
        return None

    def _reject(self, failure: PortOneWebhookFailureCode) -> NoReturn:
        self._queue_event(PaymentWebhookEvent.EventType.PAYMENT_REJECTED, reason_code=failure.value)
        raise failure.as_error()

    def _reject_and_cancel_paid_payment(self, failure: PortOneWebhookFailureCode) -> NoReturn:
        self._queue_event(PaymentWebhookEvent.EventType.PAYMENT_REJECTED, reason_code=failure.value)

        leftover_price = self.portone_payment_info["amount"] - self.portone_payment_info["cancel_amount"]
        if not (
            self.portone_payment_info["status"] == PortOneV1PaymentStatus.PAID
            and self.portone_payment_info["merchant_uid"] == self.initial_data["merchant_uid"]
            and leftover_price > 0
            and self.cart_or_order is not None
        ):
            raise failure.as_error()

        try:
            cancel_response = portone_client.req_cancel_payment(
                imp_id=self.portone_payment_info["imp_uid"],
                refund_request_price=leftover_price,
                current_leftover_price=leftover_price,
                reason=failure.label,
            )
        except (PortOneException, PortOneExceptionGroup) as e:
            self._queue_event(PaymentWebhookEvent.EventType.CANCEL_FAILED, reason_code=failure.value, exc=e)
            raise serializers.ValidationError(detail=str(e), code="portone_cancel_error") from e

        self._queue_event(
            PaymentWebhookEvent.EventType.CANCEL_SUCCEEDED,
            reason_code=failure.value,
            cancel_response=cancel_response,
        )
        raise failure.as_error()

    def _queue_event(
        self,
        event_type: PaymentWebhookEvent.EventType,
        *,
        payment_history: PaymentHistory | None = None,
        cancel_response: dict | None = None,
        reason_code: str | None = None,
        exc: BaseException | None = None,
    ) -> None:
        # cart_or_order / portone_payment_info 는 cached_property — `__dict__` 에서 직접 꺼내 추가 DB 호출을 막는다.
        # 이미 access 된 경우엔 cache hit, 아직 access 전이면 None.
        cart_or_order = self.__dict__.get("cart_or_order")
        event: dict[str, object] = {
            "event_type": event_type,
            "created_at": now_aware(),
            "request_payload": dict(self.initial_data),
            "order": cart_or_order if isinstance(cart_or_order, Order) else None,
            "single_product_cart": cart_or_order if isinstance(cart_or_order, SingleProductCart) else None,
            "payment_lookup_response": self.__dict__.get("portone_payment_info"),
            "payment_history": payment_history,
            "cancel_response": cancel_response,
            "reason_code": type(exc).__name__ if exc else reason_code,
            "reason": "".join(format_exception(exc)) if exc else None,
        }
        self._queued_webhook_events.append(event)

    @staticmethod
    def _lock_or_promote_order(merchant_uid: str) -> Order:
        """Order 가 있으면 lock 하여 반환. SingleProductCart 만 있으면 lock + to_order() 로 승격.

        모델 관계: `SingleProductCart` 는 단일 상품 장바구니의 결제 전 임시 상태이고,
        결제가 성공하면 `to_order()` 로 같은 PK 의 `Order` 로 승격되며 cart 자체는 hard delete 된다.
        webhook 은 `merchant_uid` (= shortuuid(cart/order PK) + prepared cart hash) 로 호출되므로,
        같은 PK 의 두 모델 중 현재 살아있는 쪽을 lock 한다.

        동시 webhook race 시: 첫 호출이 cart lock + to_order() commit 후, 두 번째 호출은
        cart 가 hard_delete 된 상태로 lock 해제됨 → Order 재조회에서 승격된 Order 발견.
        """
        if order := Order.objects.select_for_update().filter_by_merchant_uid(merchant_uid).first():
            return order
        if cart := SingleProductCart.objects.select_for_update().filter_by_merchant_uid(merchant_uid).first():
            return cart.to_order()
        # 두 webhook 동시 진입 race: cart lock 대기 동안 다른 thread 가 cart→Order 승격을 commit + cart hard_delete.
        # lock 해제 시점에 cart 는 비어 있고 Order 가 새로 보이므로 재조회. 동시성 테스트 `concurrent_webhook_test` 가 커버.
        if order := Order.objects.select_for_update().filter_by_merchant_uid(merchant_uid).first():
            return order
        # defensive: cart 도 Order 도 없는 상태는 validate() 에서 이미 거부됨 — 도달 시 invariant 위반.
        raise PortOneWebhookFailureCode.ORDER_NOT_FOUND.as_error()  # pragma: no cover


class PortOneV1WebhookResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="success", read_only=True)
    message = serializers.CharField(default="일반 결제 성공", read_only=True)
