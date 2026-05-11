from __future__ import annotations

import contextlib
import datetime
import hashlib
import hmac
import typing
from base64 import urlsafe_b64encode
from functools import cached_property
from uuid import uuid4

from core.const.system import SYSTEM_EMAIL, SYSTEM_USERNAME
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from rest_framework.reverse import reverse
from shortuuid import decode, encode

if typing.TYPE_CHECKING:
    from shop.order.models import OrderQuerySet


class UserExt(AbstractUser):
    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    unique_id = models.UUIDField(unique=True, editable=False, null=False, blank=False, default=uuid4)

    class Meta(AbstractUser.Meta):
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["unique_id"], name="userext_unique_id_idx")]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"

    @classmethod
    def get_system_user(cls) -> UserExt:
        return cls.objects.get_or_create(username=SYSTEM_USERNAME, email=SYSTEM_EMAIL)[0]

    @cached_property
    def short_unique_id(self) -> str:
        return encode(self.unique_id)

    @cached_property
    def salt(self) -> str:
        hmac_result = hmac.new(
            settings.SHOP.order_scancode_salt.encode(), self.unique_id.bytes, hashlib.sha256
        ).digest()
        return urlsafe_b64encode(hmac_result).decode("utf-8").rstrip("=")

    @cached_property
    def scancode_token(self) -> str:
        return f"user:{self.short_unique_id}:{self.salt}"

    @cached_property
    def scancode_path(self) -> str:
        return f"{reverse('v1:user-scancode-list')}?token={self.scancode_token}"

    @classmethod
    def from_short_unique_id(cls, short_unique_id: str) -> UserExt | None:
        with contextlib.suppress(ValueError):
            return cls.objects.filter(unique_id=decode(short_unique_id)).first()
        return None

    @classmethod
    def from_scancode_token(cls, scancode_token: str) -> UserExt | None:
        splitted_token = scancode_token.split(":")
        if len(splitted_token) != 3:
            return None

        prefix, short_unique_id, salt = splitted_token
        if prefix != "user":
            return None

        if not (short_unique_id and salt):
            return None

        if (user := cls.from_short_unique_id(short_unique_id)) and user.salt == salt:
            return user

        return None

    @property
    def purchased_orders(self) -> "OrderQuerySet":
        from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
        from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus

        return (
            Order.objects.select_related("customer_info")
            .prefetch_related(
                models.Prefetch(
                    lookup="products",
                    queryset=OrderProductRelation.objects.select_related("product").prefetch_related(
                        models.Prefetch(
                            lookup="options",
                            queryset=OrderProductOptionRelation.objects.select_related(
                                "product_option_group", "product_option"
                            ),
                        )
                    ),
                ),
                models.Prefetch(
                    "payment_histories",
                    queryset=PaymentHistory.objects.order_by("-created_at"),
                    to_attr="_payment_histories_by_latest",
                ),
            )
            .annotate(
                current_status=(
                    PaymentHistory.objects.filter(
                        order_id=models.OuterRef("id"),
                        status__in=[
                            PaymentHistoryStatus.completed,
                            PaymentHistoryStatus.partial_refunded,
                            PaymentHistoryStatus.refunded,
                        ],
                    )
                    .order_by("-created_at")
                    .values_list("status", flat=True)[:1]
                ),
            )
            .filter(
                user=self,
                current_status__in=[
                    PaymentHistoryStatus.completed,
                    PaymentHistoryStatus.partial_refunded,
                    PaymentHistoryStatus.refunded,
                ],
            )
            .order_by("-created_at")
        )

    @property
    def purchased_orders_in_last_six_months(self) -> "OrderQuerySet":
        return self.purchased_orders.filter(created_at__gte=datetime.date.today() - datetime.timedelta(days=183))
