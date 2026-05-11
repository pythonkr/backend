from core.models import BaseAbstractModel
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


class PaymentHistory(BaseAbstractModel):
    order = models.ForeignKey("order.Order", on_delete=models.PROTECT, related_name="payment_histories")
    imp_id = models.CharField(max_length=256, null=True, blank=True)

    status = models.CharField(
        max_length=32, choices=PaymentHistoryStatus.choices, default=PaymentHistoryStatus.completed
    )
    price = models.IntegerField()

    def __str__(self) -> str:
        return f"{self.order} <{self.get_status_display()}> ({self.price}원) [{self.created_at.isoformat()}]"

    class Meta:
        ordering = ("-created_at",)
        indexes = (models.Index(fields=["imp_id"]), models.Index(fields=["status"]))
