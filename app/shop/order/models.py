from __future__ import annotations

import base64
import contextlib
import datetime
import functools
import hashlib
import hmac
import typing

from core.const.shop_error_messages import NotRefundableErrorMessages
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.util.strutil import uuid_to_b64
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.manager import BaseManager
from rest_framework.reverse import reverse
from shop.payment_history.models import PaymentHistory
from shortuuid import decode, encode
from simple_history.models import HistoricalRecords

UserModel = get_user_model()


class OrderQuerySet(BaseAbstractModelQuerySet):
    def filter_has_payment_histories(self) -> models.QuerySet[Order]:
        return self.filter_active().filter(models.Exists(PaymentHistory.objects.filter(order=models.OuterRef("id"))))

    def filter_has_no_payment_histories(self) -> models.QuerySet[Order]:
        return self.filter_active().filter(~models.Exists(PaymentHistory.objects.filter(order=models.OuterRef("id"))))


class Order(BaseAbstractModel):
    user = models.ForeignKey(UserModel, on_delete=models.PROTECT)
    name = models.TextField()

    payment_histories: BaseManager[PaymentHistory]
    products: BaseManager[OrderProductRelation]

    objects: OrderQuerySet = OrderQuerySet.as_manager()  # type: ignore[assignment, misc]
    prefetchs = {
        "_payment_histories_by_latest": models.Prefetch(
            "payment_histories",
            queryset=PaymentHistory.objects.order_by("-created_at"),
            to_attr="_payment_histories_by_latest",
        ),
    }

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        cart_or_order = "CART" if self.is_cart else "ORDER"
        created_at = self.created_at.isoformat()
        return f"{self.user}의 {cart_or_order} <{self.current_status}> [{created_at}]"

    @functools.cached_property
    def first_paid_price(self) -> int:
        return sum(product.price + product.donation_price for product in self.products.all())

    @functools.cached_property
    def first_payment_history(self) -> PaymentHistory | None:
        if hasattr(self, "_payment_histories_by_latest") and self._payment_histories_by_latest:
            return self._payment_histories_by_latest[-1]

        if not (payment_histories := self.payment_histories.all()):
            return None

        return min(payment_histories, key=lambda payment_history: payment_history.created_at)

    @functools.cached_property
    def first_paid_at(self) -> datetime.datetime | None:
        return self.first_payment_history.created_at if self.first_payment_history else None

    @functools.cached_property
    def current_payment_history(self) -> PaymentHistory | None:
        if hasattr(self, "_payment_histories_by_latest") and self._payment_histories_by_latest:
            return self._payment_histories_by_latest[0]

        if not (payment_histories := self.payment_histories.all()):
            return None

        return max(payment_histories, key=lambda payment_history: payment_history.created_at)

    @functools.cached_property
    def current_paid_price(self) -> int:
        return self.current_payment_history.price if self.current_payment_history else 0

    @functools.cached_property
    def current_status(self) -> str:
        from shop.payment_history.models import PaymentHistoryStatus

        return self.current_payment_history.status if self.current_payment_history else PaymentHistoryStatus.pending

    @functools.cached_property
    def latest_imp_id(self) -> str | None:
        return self.current_payment_history.imp_id if self.current_payment_history else None

    @functools.cached_property
    def is_cart(self) -> bool:
        from shop.payment_history.models import PaymentHistoryStatus

        return self.current_status == PaymentHistoryStatus.pending

    @property
    def short_id(self) -> str:
        """
        주문 ID를 base64로 인코딩한 문자열을 반환. QR 코드 생성에 사용됩니다.
        (주문 ID의 길이를 줄여 QR 코드를 단순화하기 위함 - 길이가 길면 QR 코드가 복잡해짐)
        """
        return uuid_to_b64(self.id)

    @property
    def scancode_token(self) -> str:
        salted_order_id = f"{self.id}{settings.SHOP.order_scancode_salt}".encode()
        return hashlib.sha256(salted_order_id).hexdigest()

    @property
    def scancode_path(self) -> str:
        base_path = reverse("v1:orders-retrieve-scancode", kwargs={"order_id": self.id})
        return f"{base_path}?token={self.scancode_token}"

    @property
    def not_fully_refundable_reason(self) -> str | None:
        """
        주문 전체의 환불이 불가능한 사유를 반환합니다.
        만약 환불이 가능하다면 None을 반환합니다.
        환불이 불가능한 경우는 다음과 같습니다.
        - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
        - 이미 사용한 상품이 있는 경우
        - 환불할 상품이 없는 경우
        - 환불할 금액이 없는 경우
        - 환불할 금액이 음수인 경우
        - 환불할 금액이 남은 결제 금액과 일치하지 않는 경우
        - 환불 가능한 일자를 지난 상품이 있는 경우
        """
        from shop.payment_history.models import REFUNDABLE_STATUSES
        from shop.product.models import Product

        NOT_REFUNDABLE_PRODUCT_RELATION_STATUSES = {
            OrderProductRelation.OrderProductStatus.pending,
            OrderProductRelation.OrderProductStatus.used,
        }

        if not self.latest_imp_id:
            return NotRefundableErrorMessages.ORDER_IMP_ID_NOT_EXIST
        if self.current_status not in REFUNDABLE_STATUSES:
            return NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS

        product_relations = list[OrderProductRelation](self.products.all())
        if any(rel.status in NOT_REFUNDABLE_PRODUCT_RELATION_STATUSES for rel in product_relations):
            return NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_USED_TRY_AFTER_CHANGING_STATUS

        refund_target_product_relations = [
            rel for rel in product_relations if rel.status == OrderProductRelation.OrderProductStatus.paid
        ]
        if not refund_target_product_relations:
            return NotRefundableErrorMessages.ORDER_REFUNDABLE_PRODUCT_NOT_FOUND

        expected_refund_price = sum(rel.price + rel.donation_price for rel in refund_target_product_relations)
        if expected_refund_price == 0:
            return NotRefundableErrorMessages.ORDER_REFUNDABLE_PRICE_NOT_FOUND
        if expected_refund_price < 0:
            return NotRefundableErrorMessages.ORDER_REFUND_TARGET_PRICE_IS_NEGATIVE
        if self.current_paid_price != expected_refund_price:
            return NotRefundableErrorMessages.ORDER_REFUND_TARGET_PRICE_IS_MISMATCH

        now = datetime.datetime.now().astimezone()
        if any(typing.cast(Product, rel.product).refundable_ends_at < now for rel in refund_target_product_relations):
            return NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED

        return None


class OrderProductRelation(BaseAbstractModel):
    class OrderProductStatus(models.TextChoices):
        pending = "pending", "결제 대기 중"
        paid = "paid", "결제 완료"
        used = "used", "사용함"
        refunded = "refunded", "환불함"

    PURCHASED_STOCK_STATUS = {OrderProductStatus.paid, OrderProductStatus.used}

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="products", null=True, blank=True)
    product = models.ForeignKey("product.Product", on_delete=models.PROTECT)

    status = models.CharField(max_length=32, choices=OrderProductStatus.choices, default=OrderProductStatus.pending)
    price = models.PositiveIntegerField()
    donation_price = models.PositiveIntegerField(default=0)

    single_product_cart: SingleProductCart | None
    options: BaseManager[OrderProductOptionRelation]

    history = HistoricalRecords()

    def __str__(self) -> str:
        return f"[{self.order}] {self.product} ({self.get_status_display()})"

    @functools.cached_property
    def short_id(self) -> str:
        return encode(self.id)

    @functools.cached_property
    def salt(self) -> str:
        hmac_result = hmac.new(settings.SHOP.order_scancode_salt.encode(), self.id.bytes, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(hmac_result).decode("utf-8").rstrip("=")

    @functools.cached_property
    def scancode_token(self) -> str:
        return f"opr:{self.short_id}:{self.salt}"

    @functools.cached_property
    def scancode_path(self) -> str:
        return f"{reverse('v1:order-products-scancode-list')}?token={self.scancode_token}"

    @classmethod
    def from_short_id(cls, short_id: str) -> OrderProductRelation | None:
        with contextlib.suppress(ValueError):
            return cls.objects.filter(id=decode(short_id)).first()

        return None

    @classmethod
    def from_scancode_token(cls, scancode_token: str) -> OrderProductRelation | None:
        splitted_token = scancode_token.split(":")
        if len(splitted_token) != 3:
            return None

        prefix, short_id, salt = splitted_token
        if prefix != "opr":
            return None

        if not (short_id and salt):
            return None

        if (opr := cls.from_short_id(short_id)) and opr.salt == salt:
            return opr

        return None

    @property
    def not_refundable_reason(self) -> str | None:
        """
        상품 환불이 불가능한 사유를 반환합니다.
        만약 환불이 가능하다면 None을 반환합니다.
        환불이 불가능한 경우는 다음과 같습니다.
        - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
        - 이미 사용했거나 결제 전, 또는 환불된 상품인 경우
        - 환불 가능한 일자를 지난 상품이 있는 경우
        - 환불 금액이 없는 경우
        """
        from shop.payment_history.models import REFUNDABLE_STATUSES
        from shop.product.models import Product

        order = typing.cast(Order | None, self.order)
        if not (order and order.latest_imp_id):
            return NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE
        if order.current_status not in REFUNDABLE_STATUSES:
            return NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS
        if self.status != OrderProductRelation.OrderProductStatus.paid:
            return NotRefundableErrorMessages.PRODUCT_STATUS_IS_NOT_PAID

        if typing.cast(Product, self.product).refundable_ends_at < datetime.datetime.now().astimezone():
            return NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED

        if (self.price + self.donation_price) == 0:
            return NotRefundableErrorMessages.PRODUCT_PRICE_IS_ZERO

        return None


class OrderProductOptionRelation(BaseAbstractModel):
    order_product_relation = models.ForeignKey(OrderProductRelation, on_delete=models.CASCADE, related_name="options")
    product_option_group = models.ForeignKey("product.OptionGroup", on_delete=models.PROTECT)
    product_option = models.ForeignKey("product.Option", on_delete=models.PROTECT, null=True, blank=True)
    custom_response = models.TextField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [models.Index(fields=["custom_response"])]

    def __str__(self) -> str:
        name = self.product_option.name if self.product_option else self.custom_response
        return f"{self.product_option_group.name} - {name}"


class SingleProductCart(BaseAbstractModel):
    user = models.ForeignKey(UserModel, on_delete=models.PROTECT)
    order_product_relation = models.OneToOneField(
        OrderProductRelation,
        on_delete=models.PROTECT,
        related_name="single_product_cart",
    )

    history = HistoricalRecords()

    def to_order(self) -> Order:
        order = Order.objects.create(
            id=self.id,
            user=self.user,
            name=self.order_product_relation.product.name,
            name_ko=self.order_product_relation.product.name_ko,
            name_en=self.order_product_relation.product.name_en,
        )
        self.order_product_relation.order = order
        self.order_product_relation.save()

        CustomerInfo.objects.filter(single_product_cart=self).update(order=order, single_product_cart=None)

        # cart 가 order 로 전환되면 cart 자체는 사라져야 하므로 hard delete (의도적).
        SingleProductCart.objects.filter(id=self.id).hard_delete()

        return order

    @functools.cached_property
    def first_paid_price(self) -> int:
        return self.order_product_relation.price + self.order_product_relation.donation_price

    @functools.cached_property
    def current_payment_history(self) -> None:
        return None

    @functools.cached_property
    def current_paid_price(self) -> typing.Literal[0]:
        return 0

    @functools.cached_property
    def current_status(self) -> str:
        from shop.payment_history.models import PaymentHistoryStatus

        return PaymentHistoryStatus.pending

    @functools.cached_property
    def is_cart(self) -> typing.Literal[True]:
        return True

    @functools.cached_property
    def payment_histories(self) -> list[PaymentHistory]:
        return []

    @functools.cached_property
    def products(self) -> list[OrderProductRelation]:
        return [self.order_product_relation]

    @functools.cached_property
    def name(self) -> str:
        return self.order_product_relation.product.name


class CustomerInfo(BaseAbstractModel):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="customer_info", null=True)
    single_product_cart = models.OneToOneField(
        SingleProductCart, on_delete=models.PROTECT, related_name="customer_info", null=True
    )

    name = models.TextField()
    phone = models.TextField()
    email = models.TextField()
    organization = models.TextField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["email"]),
            models.Index(fields=["organization"]),
        ]
