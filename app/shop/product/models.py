from __future__ import annotations

import datetime
import functools
import re
import typing

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.util.dateutil import now_aware
from core.util.timespan import TimeSpan
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.manager import BaseManager
from simple_history.models import HistoricalRecords

if typing.TYPE_CHECKING:  # pragma: no cover
    from user.models import UserExt


class CategoryGroup(BaseAbstractModel):
    name = models.CharField(max_length=100)
    priority = models.IntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["priority", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["name"], name="uq__cat_grp__nm")]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Category(BaseAbstractModel):
    group = models.ForeignKey(CategoryGroup, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    priority = models.IntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["group__priority", "priority", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["group", "name"], name="uq__cat__grp_nm")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.group.name} > {self.name}"


class Tag(BaseAbstractModel):
    name = models.CharField(max_length=100)
    stock = models.IntegerField(default=0)
    max_quantity_per_user = models.IntegerField(default=0)

    products: BaseManager[Product]

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name"], name="uq__tag__nm")]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    @functools.cached_property
    def leftover_stock(self) -> int | None:
        """해당 태그에 속한 상품들의 재고를 반환합니다."""
        from shop.order.models import OrderProductRelation

        return (
            (
                self.stock
                - OrderProductRelation.objects.filter_active()
                .filter(
                    product__tags__tag=self,
                    single_product_cart__isnull=True,
                    status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
                )
                .count()
            )
            if self.stock
            else None
        )

    def get_user_taken_stock_count(self, *, user: "UserExt", include_cart: bool, include_purchased: bool) -> int:
        """해당 유저가 담거나 구매한 상품군 상품의 수량을 반환합니다."""
        from shop.order.models import OrderProductRelation

        target_status: set[OrderProductRelation.OrderProductStatus] = set()
        if include_cart:
            target_status.add(OrderProductRelation.OrderProductStatus.pending)
        if include_purchased:
            target_status |= OrderProductRelation.PURCHASED_STOCK_STATUS

        return (
            OrderProductRelation.objects.filter_active()
            .filter(
                order__user=user,
                product__tags__tag=self,
                single_product_cart__isnull=True,
                status__in=target_status,
            )
            .count()
        )


class ProductQuerySet(BaseAbstractModelQuerySet):
    def filter_visible_at(self, dt: datetime.datetime) -> typing.Self:
        return self.filter_active().filter(visible_starts_at__lte=dt, visible_ends_at__gte=dt)

    def filter_visible_now(self) -> typing.Self:
        return self.filter_visible_at(now_aware())


class Product(BaseAbstractModel):
    class CurrentStatus(models.TextChoices):
        OUT_OF_VISIBLE_PERIOD = "out_of_visible_period", "노출 기간 아님"
        OUT_OF_ORDERABLE_PERIOD = "out_of_orderable_period", "판매 기간 아님"
        ACTIVE = "active", "노출 중"

    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    image = models.ForeignKey(
        "file.PublicFile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="대표 이미지",
    )

    price = models.PositiveIntegerField()
    stock = models.IntegerField(default=0)

    max_quantity_per_user = models.IntegerField(default=0)
    visible_starts_at = models.DateTimeField(default=datetime.datetime.min)
    visible_ends_at = models.DateTimeField(default=datetime.datetime.max)
    orderable_starts_at = models.DateTimeField(default=datetime.datetime.min)
    orderable_ends_at = models.DateTimeField(default=datetime.datetime.max)
    refundable_ends_at = models.DateTimeField(default=datetime.datetime.max)

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    priority = models.IntegerField(default=0)

    donation_allowed = models.BooleanField(default=False)
    donation_min_price = models.PositiveIntegerField(default=0)
    donation_max_price = models.PositiveIntegerField(default=0)

    tag_set = models.ManyToManyField(to="Tag", through="ProductTagRelation", related_name="product_set")

    tags: BaseManager[ProductTagRelation]
    option_groups: BaseManager[OptionGroup]
    objects: ProductQuerySet = ProductQuerySet.as_manager()  # type: ignore[misc, assignment]

    class Meta:
        ordering = ["category__group__priority", "category__priority", "priority", "-created_at"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["visible_starts_at", "visible_ends_at"]),
            models.Index(fields=["orderable_starts_at", "orderable_ends_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.category} > {self.name} ({self.price}원)"

    @property
    def visible_period(self) -> TimeSpan:
        return TimeSpan(self.visible_starts_at, self.visible_ends_at)

    @property
    def orderable_period(self) -> TimeSpan:
        return TimeSpan(self.orderable_starts_at, self.orderable_ends_at)

    @property
    def current_status(self) -> "Product.CurrentStatus":
        now = now_aware()
        if (self.visible_starts_at and now < self.visible_starts_at) or (
            self.visible_ends_at and now > self.visible_ends_at
        ):
            return self.CurrentStatus.OUT_OF_VISIBLE_PERIOD

        if (self.orderable_starts_at and now < self.orderable_starts_at) or (
            self.orderable_ends_at and now > self.orderable_ends_at
        ):
            return self.CurrentStatus.OUT_OF_ORDERABLE_PERIOD

        return self.CurrentStatus.ACTIVE

    @functools.cached_property
    def leftover_stock(self) -> int | None:
        """해당 상품의 재고를 반환합니다."""
        from shop.order.models import OrderProductRelation

        return (
            (
                self.stock
                - OrderProductRelation.objects.filter_active()
                .filter(
                    product=self,
                    single_product_cart__isnull=True,
                    status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
                )
                .count()
            )
            if self.stock
            else None
        )

    def get_user_taken_stock_count(self, *, user: "UserExt", include_cart: bool, include_purchased: bool) -> int:
        """해당 유저가 담거나 구매한 상품의 수량을 반환합니다."""
        from shop.order.models import OrderProductRelation

        target_status: set[OrderProductRelation.OrderProductStatus] = set()
        if include_cart:
            target_status.add(OrderProductRelation.OrderProductStatus.pending)
        if include_purchased:
            target_status |= OrderProductRelation.PURCHASED_STOCK_STATUS

        return (
            OrderProductRelation.objects.filter_active()
            .filter(
                order__user=user,
                product=self,
                single_product_cart__isnull=True,
                status__in=target_status,
            )
            .count()
        )


class ProductTagRelation(BaseAbstractModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="products")

    class Meta:
        unique_together = ["product", "tag"]

    history = HistoricalRecords()


class OptionGroupQuerySet(BaseAbstractModelQuerySet):
    def filter_visible_at(self, dt: datetime.datetime) -> typing.Self:
        return self.filter_active().filter(
            (Q(visible_starts_at__isnull=True) | Q(visible_starts_at__lte=dt))
            & (Q(visible_ends_at__isnull=True) | Q(visible_ends_at__gte=dt))
        )

    def filter_visible_now(self) -> typing.Self:
        return self.filter_visible_at(now_aware())


class OptionGroup(BaseAbstractModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="option_groups")
    priority = models.IntegerField(default=0)

    name = models.CharField(max_length=100)
    min_quantity_per_product = models.IntegerField(default=0)
    max_quantity_per_product = models.IntegerField(default=0)
    max_quantity_per_user = models.IntegerField(default=0)

    # nullable — None 이면 Product 의 동일 필드를 따른다.
    visible_starts_at = models.DateTimeField(null=True, blank=True)
    visible_ends_at = models.DateTimeField(null=True, blank=True)
    orderable_starts_at = models.DateTimeField(null=True, blank=True)
    orderable_ends_at = models.DateTimeField(null=True, blank=True)

    is_custom_response = models.BooleanField(default=False)
    custom_response_pattern = models.TextField(null=True, blank=True)
    response_modifiable_ends_at = models.DateTimeField(
        default=None,
        null=True,
        help_text="답변 수정 마감 시간. None인 경우 수정 불가.",
    )

    objects: OptionGroupQuerySet = OptionGroupQuerySet.as_manager()  # type: ignore[misc, assignment]

    class Meta:
        ordering = ["priority", "-created_at"]
        unique_together = ["product", "name"]
        indexes = [
            models.Index(fields=["visible_starts_at", "visible_ends_at"]),
            models.Index(fields=["orderable_starts_at", "orderable_ends_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.product.name}] {self.name}"

    def clean(self) -> None:
        # is_custom_response=True 시 패턴이 admin 계약 — 빈 답변 허용은 ".*", 비공란 강제는 ".+" 등으로 명시.
        if self.is_custom_response and not self.custom_response_pattern:
            raise ValidationError(
                {"custom_response_pattern": "is_custom_response=True 일 때 custom_response_pattern 은 필수입니다."}
            )
        if self.custom_response_pattern:
            try:
                re.compile(self.custom_response_pattern)
            except re.error as exc:
                raise ValidationError({"custom_response_pattern": f"유효하지 않은 정규표현식입니다: {exc}"}) from exc
        super().clean()

    @property
    def effective_visible_period(self) -> TimeSpan:
        """그룹 값이 있으면 그것, 없으면 Product 값으로 fallback."""
        return TimeSpan(
            self.visible_starts_at or self.product.visible_starts_at,
            self.visible_ends_at or self.product.visible_ends_at,
        )

    @property
    def effective_orderable_period(self) -> TimeSpan:
        """그룹 값이 있으면 그것, 없으면 Product 값으로 fallback."""
        return TimeSpan(
            self.orderable_starts_at or self.product.orderable_starts_at,
            self.orderable_ends_at or self.product.orderable_ends_at,
        )

    def is_visible_now(self) -> bool:
        return now_aware() in self.effective_visible_period

    def is_orderable_now(self) -> bool:
        return now_aware() in self.effective_orderable_period

    def get_user_taken_stock_count(self, *, user: "UserExt", include_cart: bool, include_purchased: bool) -> int:
        """해당 유저가 이 옵션 그룹 안에서 담거나 구매한 옵션의 총 수량을 반환합니다."""
        from shop.order.models import OrderProductOptionRelation, OrderProductRelation

        target_status: set[OrderProductRelation.OrderProductStatus] = set()
        if include_cart:
            target_status.add(OrderProductRelation.OrderProductStatus.pending)
        if include_purchased:
            target_status |= OrderProductRelation.PURCHASED_STOCK_STATUS

        return (
            OrderProductOptionRelation.objects.filter_active()
            .filter(
                order_product_relation__order__user=user,
                order_product_relation__single_product_cart__isnull=True,
                order_product_relation__status__in=target_status,
                order_product_relation__deleted_at__isnull=True,
                product_option_group=self,
            )
            .count()
        )

    def is_group_stock_available(self) -> bool:
        """해당 옵션 그룹의 재고가 있는지 확인합니다."""
        active_options = list(self.options.filter_active())
        if (
            self.is_custom_response
            or not self.min_quantity_per_product
            or any(option.leftover_stock is None for option in active_options)
        ):
            # 주문당 필수 구매 개수가 없거나 재고가 무한대인 옵션이 하나라도 있으면 재고가 충분하다고 판단합니다.
            return True

        # 모든 옵션의 재고를 합쳐서 해당 옵션 그룹의 최소 구매 수량과 비교했을 시,
        # 최소 구매 수량보다 크거나 같으면 재고가 충분하다고 판단합니다.
        return self.min_quantity_per_product <= sum(option.leftover_stock for option in active_options)


class Option(BaseAbstractModel):
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, related_name="options")
    priority = models.IntegerField(default=0)

    name = models.CharField(max_length=100)
    max_quantity_per_user = models.IntegerField(default=0)

    additional_price = models.PositiveIntegerField(default=0)
    stock = models.IntegerField(default=0)

    class Meta:
        ordering = ["priority", "-created_at"]
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.additional_price}원)"

    @functools.cached_property
    def leftover_stock(self) -> int | None:
        """해당 옵션의 재고를 반환합니다."""
        from shop.order.models import OrderProductOptionRelation, OrderProductRelation

        return (
            (
                self.stock
                - OrderProductOptionRelation.objects.filter_active()
                .filter(
                    product_option=self,
                    order_product_relation__single_product_cart__isnull=True,
                    order_product_relation__deleted_at__isnull=True,
                    order_product_relation__status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
                )
                .count()
            )
            if self.stock
            else None
        )

    def get_user_taken_stock_count(self, *, user: "UserExt", include_cart: bool, include_purchased: bool) -> int:
        """해당 유저가 담거나 구매한 옵션의 수량을 반환합니다."""
        from shop.order.models import OrderProductOptionRelation, OrderProductRelation

        target_status: set[OrderProductRelation.OrderProductStatus] = set()
        if include_cart:
            target_status.add(OrderProductRelation.OrderProductStatus.pending)
        if include_purchased:
            target_status |= OrderProductRelation.PURCHASED_STOCK_STATUS

        return (
            OrderProductOptionRelation.objects.filter_active()
            .filter(
                order_product_relation__order__user=user,
                order_product_relation__single_product_cart__isnull=True,
                order_product_relation__deleted_at__isnull=True,
                order_product_relation__status__in=target_status,
                product_option=self,
            )
            .count()
        )
