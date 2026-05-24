from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from shop.product.models import Option, OptionGroup, Product


def _min_ignoring_none(values: Iterable[int | None]) -> int | None:
    return min(finite) if (finite := [v for v in values if v is not None]) else None


@dataclass(frozen=True)
class StockContext:
    """Product 페이지에 등장하는 모든 product / option / group 의 점유 수량을 단일 stage 에서 prefetch 한 결과"""

    covered_product_ids: frozenset[UUID] = field(default_factory=frozenset)
    global_product_purchased: Counter[UUID] = field(default_factory=Counter)
    global_option_purchased: Counter[UUID] = field(default_factory=Counter)
    user_product_taken: Counter[UUID] = field(default_factory=Counter)
    user_group_taken: Counter[UUID] = field(default_factory=Counter)
    user_option_taken: Counter[UUID] = field(default_factory=Counter)

    @staticmethod
    def _leftover_under_limit(limit: int, taken: int) -> int | None:
        """`max_quantity_per_user` 류 한도 1건당 남은 수량. 0 = 무제한 sentinel → None."""
        return max(0, limit - taken) if limit > 0 else None

    def product_leftover_stock(self, product: Product) -> int | None:
        if not product.stock:
            return None
        if product.id not in self.covered_product_ids:
            return product.leftover_stock
        return product.stock - self.global_product_purchased[product.id]

    def option_leftover_stock(self, option: Option) -> int | None:
        if not option.stock:
            return None
        if option.group.product_id not in self.covered_product_ids:
            return option.leftover_stock
        return option.stock - self.global_option_purchased[option.id]

    def _product_and_group_leftover_info(self, group: OptionGroup) -> dict[str, int | None]:
        return {
            "product_max_quantity_per_user": self._leftover_under_limit(
                group.product.max_quantity_per_user, self.user_product_taken[group.product_id]
            ),
            "product_leftover_stock": self.product_leftover_stock(group.product),
            "option_group_max_quantity_per_user": self._leftover_under_limit(
                group.max_quantity_per_user, self.user_group_taken[group.id]
            ),
        }

    def option_leftover_info(self, option: Option) -> dict[str, int | None]:
        return self._product_and_group_leftover_info(option.group) | {
            "option_max_quantity_per_user": self._leftover_under_limit(
                option.max_quantity_per_user, self.user_option_taken[option.id]
            ),
            "option_leftover_stock": self.option_leftover_stock(option),
        }

    def option_group_leftover_info(self, group: OptionGroup) -> dict[str, int | None]:
        return self._product_and_group_leftover_info(group)


# context 미주입 시 (직접 DTO 인스턴스화 등) 의 default. frozen + 빈 Counter 라 공유 안전.
_EMPTY_STOCK_CONTEXT = StockContext()


class OptionLeftoverStockInfo(serializers.Serializer):
    """OptionDto.leftover_stock_info dict 의 OpenAPI 스키마 — drf-spectacular 가 키를 명시화하도록.

    각 값은 해당 한도가 남긴 잔여 수량. None 은 "무제한 / 미적용" (한도가 0 sentinel 이거나 stock 무한).
    """

    product_max_quantity_per_user = serializers.IntegerField(allow_null=True)
    product_leftover_stock = serializers.IntegerField(allow_null=True)
    option_group_max_quantity_per_user = serializers.IntegerField(allow_null=True)
    option_max_quantity_per_user = serializers.IntegerField(allow_null=True)
    option_leftover_stock = serializers.IntegerField(allow_null=True)


class OptionGroupLeftoverStockInfo(serializers.Serializer):
    """OptionGroupDto.leftover_stock_info dict 의 OpenAPI 스키마 — 그룹 레벨 한도 3개만."""

    product_max_quantity_per_user = serializers.IntegerField(allow_null=True)
    product_leftover_stock = serializers.IntegerField(allow_null=True)
    option_group_max_quantity_per_user = serializers.IntegerField(allow_null=True)


class OptionDto(serializers.ModelSerializer):
    leftover_stock = serializers.SerializerMethodField()
    leftover_stock_per_user = serializers.SerializerMethodField()
    leftover_stock_info = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "id",
            "name",
            "additional_price",
            "max_quantity_per_user",
            "leftover_stock",
            "leftover_stock_per_user",
            "leftover_stock_info",
        )
        model = Option

    def get_leftover_stock(self, option: Option) -> int | None:
        return self.context.get("stock_context", _EMPTY_STOCK_CONTEXT).option_leftover_stock(option)

    @extend_schema_field(OptionLeftoverStockInfo)
    def get_leftover_stock_info(self, option: Option) -> dict[str, int | None]:
        return self.context.get("stock_context", _EMPTY_STOCK_CONTEXT).option_leftover_info(option)

    def get_leftover_stock_per_user(self, option: Option) -> int | None:
        return _min_ignoring_none(self.get_leftover_stock_info(option).values())


class OptionGroupDto(serializers.ModelSerializer):
    options = OptionDto(many=True)
    leftover_stock_per_user = serializers.SerializerMethodField()
    leftover_stock_info = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "id",
            "name",
            "min_quantity_per_product",
            "max_quantity_per_product",
            "max_quantity_per_user",
            "visible_starts_at",
            "visible_ends_at",
            "orderable_starts_at",
            "orderable_ends_at",
            "is_custom_response",
            "custom_response_pattern",
            "leftover_stock_per_user",
            "leftover_stock_info",
            "options",
        )
        model = OptionGroup

    @extend_schema_field(OptionGroupLeftoverStockInfo)
    def get_leftover_stock_info(self, group: OptionGroup) -> dict[str, int | None]:
        return self.context.get("stock_context", _EMPTY_STOCK_CONTEXT).option_group_leftover_info(group)

    def get_leftover_stock_per_user(self, group: OptionGroup) -> int | None:
        return _min_ignoring_none(self.get_leftover_stock_info(group).values())


class ProductDto(serializers.ModelSerializer):
    category_group = serializers.CharField(source="category.group.name")
    category = serializers.CharField(source="category.name")
    image = serializers.FileField(source="image.file", read_only=True, allow_null=True)
    option_groups = OptionGroupDto(many=True)
    tag_names: serializers.StringRelatedField = serializers.StringRelatedField(source="tags", many=True)
    leftover_stock = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "id",
            "name",
            "description",
            "image",
            "price",
            "donation_allowed",
            "donation_min_price",
            "donation_max_price",
            "orderable_starts_at",
            "orderable_ends_at",
            "refundable_ends_at",
            "category_group",
            "category",
            "option_groups",
            "leftover_stock",
            "tag_names",
        )
        model = Product

    def get_leftover_stock(self, product: Product) -> int | None:
        return self.context.get("stock_context", _EMPTY_STOCK_CONTEXT).product_leftover_stock(product)
