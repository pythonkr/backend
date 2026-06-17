from __future__ import annotations

import datetime
import functools
import json
import typing
from base64 import urlsafe_b64encode
from collections.abc import Iterable
from contextlib import suppress
from hashlib import sha256
from hmac import new as hmac_new
from urllib.parse import urljoin
from uuid import UUID, uuid4

import shortuuid
from core.const.shop_error_messages import NotRefundableErrorMessages
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.scancode_mixin import ScanCodeMixin
from core.util.dateutil import now_aware
from core.util.strutil import format_korean_date_period
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models.manager import BaseManager
from document.issuable import IssuableMixin
from document.models import DocumentType, IssuedDocument
from shop.payment_history.models import PURCHASED_STATUSES, PaymentHistory
from simple_history.models import HistoricalRecords

UserModel = get_user_model()
PAYMENT_HASH_LENGTH = 16


class PaymentPreparationMixin:
    id: UUID
    prepared_cart_snapshot: dict[str, typing.Any] | None
    prepared_cart_hash: str | None
    first_paid_price: int
    products: typing.Any

    @property
    def merchant_uid(self) -> str | None:
        return f"{shortuuid.encode(self.id)}.{self.prepared_cart_hash}" if self.prepared_cart_hash else None

    @property
    def prepared_price(self) -> int | None:
        return self.prepared_cart_snapshot["price"] if self.prepared_cart_snapshot else None

    def get_current_cart_snapshot(self, *, attempt: dict[str, str] | None = None) -> dict[str, typing.Any]:
        products = self.products.filter_active().prefetch_related(
            models.Prefetch("options", queryset=OrderProductOptionRelation.objects.filter_active()),
        )
        return {
            "attempt": attempt or {"id": str(uuid4()), "prepared_at": now_aware().isoformat()},
            "price": self.first_paid_price,
            "products": [
                {
                    "id": str(product_rel.id),
                    "product": str(product_rel.product_id),
                    "price": product_rel.price,
                    "donation_price": product_rel.donation_price,
                    "options": [
                        {
                            "id": str(option_rel.id),
                            "product_option_group": str(option_rel.product_option_group_id),
                            "product_option": (
                                str(option_rel.product_option_id) if option_rel.product_option_id is not None else None
                            ),
                            "custom_response": option_rel.custom_response,
                        }
                        for option_rel in sorted(product_rel.options.all(), key=lambda option_rel: str(option_rel.id))
                    ],
                }
                for product_rel in sorted(products, key=lambda rel: str(rel.id))
            ],
        }

    @staticmethod
    def _compute_cart_hash(snapshot: dict[str, typing.Any]) -> str:
        digest = hmac_new(
            settings.SECRET_KEY.encode(),
            json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(),
            sha256,
        ).digest()
        return urlsafe_b64encode(digest[:12]).decode().rstrip("=")

    def get_current_cart_hash(self, *, attempt: dict[str, str] | None = None) -> str:
        return self._compute_cart_hash(self.get_current_cart_snapshot(attempt=attempt))

    def prepare_payment(self) -> None:
        snapshot = self.get_current_cart_snapshot()
        self.prepared_cart_snapshot = snapshot
        self.prepared_cart_hash = self._compute_cart_hash(snapshot)
        self.save(update_fields={"prepared_cart_snapshot", "prepared_cart_hash"})

    def matches_payment_preparation(self, merchant_uid: str, amount: int | float) -> bool:
        if not self.prepared_cart_snapshot:
            return False
        try:
            amount_int = int(amount)
        except (TypeError, ValueError):
            return False
        attempt = self.prepared_cart_snapshot.get("attempt")
        if not isinstance(attempt, dict):
            return False
        return (
            self.merchant_uid == merchant_uid
            and amount == self.prepared_price == amount_int
            and self.prepared_cart_hash == self.get_current_cart_hash(attempt=attempt)
        )


class BaseCartQuerySet(BaseAbstractModelQuerySet):
    def filter_by_merchant_uid(self, merchant_uid: object) -> models.QuerySet:
        with suppress(AttributeError, TypeError, ValueError):
            encoded_id, cart_hash = merchant_uid.split(".", 1)
            return self.filter_active().filter(id=shortuuid.decode(encoded_id), prepared_cart_hash=cart_hash)
        return self.none()


class OrderQuerySet(BaseCartQuerySet):
    def filter_has_payment_histories(self) -> models.QuerySet[Order]:
        return self.filter_active().filter(
            models.Exists(PaymentHistory.objects.filter_active().filter(order=models.OuterRef("id")))
        )

    def filter_has_no_payment_histories(self) -> models.QuerySet[Order]:
        return self.filter_active().filter(
            ~models.Exists(PaymentHistory.objects.filter_active().filter(order=models.OuterRef("id")))
        )

    def order_by_first_paid_at(self) -> models.QuerySet[Order]:
        """첫 결제(최초 active payment_history) 시각이 최근인 주문이 먼저 오도록 정렬."""
        return self.annotate(
            _first_paid_at=PaymentHistory.objects.filter_active()
            .filter(order_id=models.OuterRef("id"))
            .order_by("created_at")
            .values("created_at")[:1]
        ).order_by(models.F("_first_paid_at").desc(nulls_last=True), "-created_at")

    def for_dto_response(self) -> models.QuerySet[Order]:
        return self.select_related("customer_info").with_dto_prefetches()

    def with_dto_prefetches(self) -> models.QuerySet[Order]:
        """OrderDto 직렬화에 필요한 active row 들을 `to_attr` 로 prefetch."""
        return self.prefetch_related(
            models.Prefetch(
                "payment_histories",
                queryset=PaymentHistory.objects.filter_active(),
                to_attr="_active_payment_histories",
            ),
            models.Prefetch(
                "products",
                queryset=(
                    OrderProductRelation.objects.filter_active()
                    .select_related("product__category", "ticket_info")
                    .prefetch_related(
                        models.Prefetch(
                            "options",
                            queryset=OrderProductOptionRelation.objects.filter_active().select_related(
                                "product_option_group",
                                "product_option",
                            ),
                        ),
                        models.Prefetch("issued_documents", queryset=IssuedDocument.objects.filter_active()),
                    )
                ),
                to_attr="_active_products",
            ),
        )

    def filter_purchased_by(self, user: UserModel) -> models.QuerySet[Order]:
        """결제 완료/부분환불/환불된 (terminal status) 주문을 user 별로 필터."""
        return (
            self.filter_active()
            .select_related("customer_info")
            .with_dto_prefetches()
            .annotate(
                current_status=(
                    PaymentHistory.objects.filter_active()
                    .filter(order_id=models.OuterRef("id"), status__in=PURCHASED_STATUSES)
                    .order_by("-created_at")
                    .values_list("status", flat=True)[:1]
                ),
            )
            .filter(user=user, current_status__in=PURCHASED_STATUSES)
            .order_by("-created_at")
        )

    def filter_in_last_six_months(self) -> models.QuerySet[Order]:
        return self.filter(created_at__gte=datetime.date.today() - datetime.timedelta(days=183))


class Order(PaymentPreparationMixin, ScanCodeMixin, BaseAbstractModel):
    scancode_prefix = "order"

    user = models.ForeignKey(UserModel, on_delete=models.PROTECT)
    name = models.TextField()
    prepared_cart_snapshot = models.JSONField(null=True, blank=True)
    prepared_cart_hash = models.CharField(max_length=PAYMENT_HASH_LENGTH, null=True, blank=True)

    payment_histories: BaseManager[PaymentHistory]
    products: BaseManager[OrderProductRelation]

    objects: OrderQuerySet = OrderQuerySet.as_manager()  # type: ignore[assignment, misc]
    prefetchs = {
        "_active_payment_histories": models.Prefetch(
            "payment_histories",
            queryset=PaymentHistory.objects.filter_active(),
            to_attr="_active_payment_histories",
        ),
    }

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover
        cart_or_order = "CART" if self.is_cart else "ORDER"
        created_at = self.created_at.isoformat()
        return f"{self.user}의 {cart_or_order} <{self.current_status}> [{created_at}]"

    @property
    def active_products(self) -> list[OrderProductRelation]:
        if hasattr(self, "_active_products"):
            return self._active_products
        return list(self.products.filter_active())

    @property
    def active_payment_histories(self) -> list[PaymentHistory]:
        if hasattr(self, "_active_payment_histories"):
            return self._active_payment_histories
        return list(self.payment_histories.filter_active())

    @functools.cached_property
    def first_paid_price(self) -> int:
        return sum(product.price + product.donation_price for product in self.active_products)

    @functools.cached_property
    def first_payment_history(self) -> PaymentHistory | None:
        if not (payment_histories := self.active_payment_histories):
            return None
        return min(payment_histories, key=lambda payment_history: payment_history.created_at)

    @functools.cached_property
    def first_paid_at(self) -> datetime.datetime | None:
        return self.first_payment_history.created_at if self.first_payment_history else None

    @functools.cached_property
    def current_payment_history(self) -> PaymentHistory | None:
        if not (payment_histories := self.active_payment_histories):
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

    def build_notification_context(self) -> dict:
        """결제 완료 알림 (auto + admin manual) 에서 공통으로 사용하는 Order-derived context.

        `first_paid_at` 은 isoformat 문자열로 변환 — JSONField 저장 시 psycopg `json.dumps` 가
        datetime 을 직접 직렬화 못함. 호출자는 customer_info 존재를 사전 검증해야 함.
        """
        customer_info = self.customer_info
        return {
            "order_name": self.name,
            "first_paid_at": self.first_paid_at.isoformat() if self.first_paid_at else None,
            "first_paid_price": self.first_paid_price,
            "customer_name": customer_info.name,
            "customer_phone": customer_info.phone,
            "customer_email": customer_info.email,
            "scancode_url": urljoin(settings.BACKEND_DOMAIN, self.scancode_path),
        }

    @functools.cached_property
    def is_cart(self) -> bool:
        from shop.payment_history.models import PaymentHistoryStatus

        return self.current_status == PaymentHistoryStatus.pending

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
        - 환불 가능한 일자를 지났거나 환불 불가(refundable_ends_at=null)인 상품이 있는 경우
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

        product_relations = self.active_products
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
        if self.current_paid_price != expected_refund_price:
            return NotRefundableErrorMessages.ORDER_REFUND_TARGET_PRICE_IS_MISMATCH

        now = now_aware()
        for rel in refund_target_product_relations:
            refundable_ends_at = typing.cast(Product, rel.product).refundable_ends_at
            if refundable_ends_at is None:
                return NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_NOT_REFUNDABLE
            if refundable_ends_at < now:
                return NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED

        return None


class OrderProductRelation(ScanCodeMixin, IssuableMixin, BaseAbstractModel):
    ISSUED_DOCUMENT_TYPE = DocumentType.confirmation_of_participation
    scancode_prefix = "opr"

    class OrderProductStatus(models.TextChoices):
        pending = "pending", "결제 대기 중"
        paid = "paid", "결제 완료"
        used = "used", "사용함"
        refunded = "refunded", "환불함"

    PURCHASED_STOCK_STATUS = {OrderProductStatus.paid, OrderProductStatus.used}
    PURCHASED_OR_REFUNDED_STATUS = PURCHASED_STOCK_STATUS | {OrderProductStatus.refunded}

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="products", null=True, blank=True)
    product = models.ForeignKey("product.Product", on_delete=models.PROTECT)

    status = models.CharField(max_length=32, choices=OrderProductStatus.choices, default=OrderProductStatus.pending)
    price = models.PositiveIntegerField()
    donation_price = models.PositiveIntegerField(default=0)

    single_product_cart: SingleProductCart | None
    options: BaseManager[OrderProductOptionRelation]

    issued_documents = GenericRelation(
        "document.IssuedDocument",
        content_type_field="issuable_content_type",
        object_id_field="issuable_object_id",
    )
    history = HistoricalRecords()

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.order}] {self.product} ({self.get_status_display()})"

    def save(  # type: ignore[override]
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
        clear_parent_preparation: bool = True,
    ) -> None:
        super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)
        if clear_parent_preparation:
            self._clear_parent_payment_preparation()

    def delete(self, using: str | None = None) -> None:
        self._clear_parent_payment_preparation()
        super().delete(using=using)

    def _clear_parent_payment_preparation(self) -> None:
        if self.status != OrderProductRelation.OrderProductStatus.pending:
            return

        # `filter().update()` — snapshot 이 존재하는 row 만 매칭하는 단일 UPDATE.
        # 대부분의 cart 편집은 snapshot 없는 상태라 fetch 없이 0 row UPDATE 로 끝남.
        has_snapshot = models.Q(prepared_cart_snapshot__isnull=False) | models.Q(prepared_cart_hash__isnull=False)
        cleared = {"prepared_cart_snapshot": None, "prepared_cart_hash": None}

        if self.order_id:
            Order.objects.filter(id=self.order_id).filter(has_snapshot).update(**cleared)
            return
        SingleProductCart.objects.filter(order_product_relation_id=self.id).filter(has_snapshot).update(**cleared)

    @property
    def not_refundable_reason(self) -> str | None:
        """
        상품 환불이 불가능한 사유를 반환합니다.
        만약 환불이 가능하다면 None을 반환합니다.
        환불이 불가능한 경우는 다음과 같습니다.
        - 주문에 PortOne ID가 없는 경우 (보통 결제가 완료되지 않았거나 주문 불러오기로 생성한 주문인 경우입니다.)
        - 이미 사용했거나 결제 전, 또는 환불된 상품인 경우
        - 환불 가능한 일자를 지났거나 환불 불가(refundable_ends_at=null)인 상품인 경우
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

        refundable_ends_at = typing.cast(Product, self.product).refundable_ends_at
        if refundable_ends_at is None:
            return NotRefundableErrorMessages.PRODUCT_IS_NOT_REFUNDABLE
        if refundable_ends_at < now_aware():
            return NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED

        if (self.price + self.donation_price) == 0:
            return NotRefundableErrorMessages.PRODUCT_PRICE_IS_ZERO

        return None

    def build_document_context(self) -> dict:
        try:
            participant = self.ticket_info
        except TicketInfo.DoesNotExist:
            participant = getattr(self.order or self.single_product_cart, "customer_info", None)
        event = self.product.category.event
        return {
            "event_name": event.name_ko,
            "event_name_en": event.name_en,
            "event_date": format_korean_date_period(event.event_start_at, event.event_end_at),
            "participant_name": (participant.name if participant else "") or "",
            "organization": (participant.organization if participant else "") or "",
            "email": (participant.email if participant else "") or "",
        }

    def build_verify_display(self, context: dict) -> dict[str, str]:
        return {
            "참가자명": context.get("participant_name", ""),
            "소속": context.get("organization", ""),
            "이메일": context.get("email", ""),
            "행사명": context.get("event_name", ""),
            "행사 일시": context.get("event_date", ""),
        }

    def is_document_downloadable_by(self, user) -> bool:
        return self.order is not None and self.order.user_id == user.id and self.is_document_valid()

    def is_document_valid(self) -> bool:
        return (
            self.status == OrderProductRelation.OrderProductStatus.used
            and self.product.category.is_ticket
            and self.product.category.event_id is not None
        )


class OrderProductOptionRelation(BaseAbstractModel):
    order_product_relation = models.ForeignKey(OrderProductRelation, on_delete=models.CASCADE, related_name="options")
    product_option_group = models.ForeignKey("product.OptionGroup", on_delete=models.PROTECT)
    product_option = models.ForeignKey("product.Option", on_delete=models.PROTECT, null=True, blank=True)
    custom_response = models.TextField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [models.Index(fields=["custom_response"])]

    def __str__(self) -> str:  # pragma: no cover
        name = self.product_option.name if self.product_option else self.custom_response
        return f"{self.product_option_group.name} - {name}"

    def save(  # type: ignore[override]
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)
        self._clear_parent_payment_preparation()

    def delete(self, using: str | None = None) -> None:
        self._clear_parent_payment_preparation()
        super().delete(using=using)

    def _clear_parent_payment_preparation(self) -> None:
        order_product_relation = self.order_product_relation
        if order_product_relation.status != OrderProductRelation.OrderProductStatus.pending:
            return
        order_product_relation._clear_parent_payment_preparation()


class SingleProductCartQuerySet(BaseCartQuerySet):
    pass


class SingleProductCart(PaymentPreparationMixin, BaseAbstractModel):
    user = models.ForeignKey(UserModel, on_delete=models.PROTECT)
    order_product_relation = models.OneToOneField(
        OrderProductRelation,
        on_delete=models.PROTECT,
        related_name="single_product_cart",
    )
    prepared_cart_snapshot = models.JSONField(null=True, blank=True)
    prepared_cart_hash = models.CharField(max_length=PAYMENT_HASH_LENGTH, null=True, blank=True)

    objects: SingleProductCartQuerySet = SingleProductCartQuerySet.as_manager()  # type: ignore[assignment, misc]

    history = HistoricalRecords()

    def to_order(self) -> Order:
        order = Order.objects.create(
            id=self.id,
            user=self.user,
            name=self.order_product_relation.product.name,
            name_ko=self.order_product_relation.product.name_ko,
            name_en=self.order_product_relation.product.name_en,
            prepared_cart_snapshot=self.prepared_cart_snapshot,
            prepared_cart_hash=self.prepared_cart_hash,
        )
        self.order_product_relation.order = order
        # cart→Order 승격은 결제 직전 단계이므로 prepared snapshot 을 유지한 채 OPR 의 parent FK 만 갱신.
        self.order_product_relation.save(clear_parent_preparation=False)

        CustomerInfo.objects.filter_active().filter(single_product_cart=self).update(
            order=order, single_product_cart=None
        )

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

    @property
    def products(self) -> models.QuerySet[OrderProductRelation]:
        return (
            OrderProductRelation.objects.filter_active()
            .select_related("product", "ticket_info")
            .filter(id=self.order_product_relation_id)
        )

    @functools.cached_property
    def active_products(self) -> list[OrderProductRelation]:
        return list(self.products)

    @functools.cached_property
    def active_payment_histories(self) -> list[PaymentHistory]:
        return []

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


class TicketInfo(BaseAbstractModel):
    order_product_relation = models.OneToOneField(
        OrderProductRelation, on_delete=models.PROTECT, related_name="ticket_info"
    )

    name = models.TextField()
    phone = models.TextField()
    email = models.TextField()
    organization = models.TextField(null=True, blank=True)
    contribution_message = models.TextField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["email"]),
            models.Index(fields=["organization"]),
        ]
