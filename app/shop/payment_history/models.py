from uuid import uuid4

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.db import models


class PaymentHistoryStatus(models.TextChoices):
    pending = "pending", "결제 대기 중"
    completed = "completed", "결제 완료"
    partial_refunded = "partial_refunded", "부분 환불함"
    refunded = "refunded", "전액 환불함"


REFUNDABLE_STATUSES: set[PaymentHistoryStatus] = {
    PaymentHistoryStatus.completed,
    PaymentHistoryStatus.partial_refunded,
}
PURCHASED_STATUSES: set[PaymentHistoryStatus] = REFUNDABLE_STATUSES | {PaymentHistoryStatus.refunded}
LEGAL_PAYMENT_STATUS_TRANSITIONS: dict[PaymentHistoryStatus, set[PaymentHistoryStatus]] = {
    PaymentHistoryStatus.pending: {PaymentHistoryStatus.completed},
    PaymentHistoryStatus.completed: {PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.refunded},
    PaymentHistoryStatus.partial_refunded: {PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.refunded},
    PaymentHistoryStatus.refunded: set(),  # terminal
}


def is_legal_payment_status_transition(current: PaymentHistoryStatus, next_: PaymentHistoryStatus) -> bool:
    return next_ in LEGAL_PAYMENT_STATUS_TRANSITIONS.get(current, set())


class PaymentHistoryQuerySet(BaseAbstractModelQuerySet):
    def latest_per_order_field(self, field_name: str, *, outer_field: str = "id") -> "PaymentHistoryQuerySet":
        return (
            self.filter_active()
            .order_by("order_id", "-created_at")
            .distinct("order_id")
            .filter(order_id=models.OuterRef(outer_field))
            .values(field_name)[:1]
        )


class PaymentHistory(BaseAbstractModel):
    order = models.ForeignKey("order.Order", on_delete=models.PROTECT, related_name="payment_histories")
    imp_id = models.CharField(max_length=256, null=True, blank=True)

    status = models.CharField(
        max_length=32, choices=PaymentHistoryStatus.choices, default=PaymentHistoryStatus.completed
    )
    price = models.IntegerField()

    objects: PaymentHistoryQuerySet = PaymentHistoryQuerySet.as_manager()  # type: ignore[assignment, misc]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.order} <{self.get_status_display()}> ({self.price}원) [{self.created_at.isoformat()}]"

    class Meta:
        ordering = ("-created_at",)
        indexes = (models.Index(fields=["imp_id"]), models.Index(fields=["status"]))


class PaymentWebhookEvent(models.Model):
    class EventType(models.TextChoices):
        WEBHOOK_RECEIVED = "webhook_received", "Webhook received"
        PAYMENT_LOOKUP_SUCCEEDED = "payment_lookup_succeeded", "Payment lookup succeeded"
        PAYMENT_LOOKUP_FAILED = "payment_lookup_failed", "Payment lookup failed"
        PAYMENT_ACCEPTED = "payment_accepted", "Payment accepted"
        PAYMENT_REJECTED = "payment_rejected", "Payment rejected"
        CANCEL_SUCCEEDED = "cancel_succeeded", "Cancel succeeded"
        CANCEL_FAILED = "cancel_failed", "Cancel failed"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    order = models.ForeignKey("order.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    single_product_cart = models.ForeignKey(
        "order.SingleProductCart", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    payment_history = models.ForeignKey(
        PaymentHistory, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    event_type = models.CharField(max_length=64, choices=EventType.choices)
    reason_code = models.CharField(max_length=128, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    request_payload = models.JSONField(null=True, blank=True)
    payment_lookup_response = models.JSONField(null=True, blank=True)
    cancel_response = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=["event_type"]),
            models.Index(fields=["reason_code"]),
        )
