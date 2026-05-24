import functools
import typing
from collections import Counter

from core.const.shop_error_messages import (
    CriticalErrorMessages,
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
)
from core.serializer.nested_model_serializer import InstanceListSerializer
from core.util.dateutil import now_aware
from django.db import transaction
from rest_framework import request, serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.product.models import Option, Product
from shop.serializers.cart_validation._base import OrderableCheckSerializerMode
from shop.serializers.cart_validation.option import OptionOrderableCheckSerializer, OptionOrderableCheckTypedDict
from shop.serializers.cart_validation.tag import TagOrderableCheckSerializer
from user.models import UserExt


class ProductOrderableCheckBeforeValidationDataType(typing.TypedDict):
    product: Product
    options: list[OptionOrderableCheckTypedDict]
    donation_price: typing.NotRequired[int]


class ProductOrderableCheckAfterValidationDataType(typing.TypedDict):
    product: Product
    options: list[OptionOrderableCheckTypedDict]
    donation_price: int


class ProductOrderableCheckSerializer(serializers.ModelSerializer):
    """장바구니에 담긴 상품 + 옵션이 주문 가능한지 확인.

    ==================== 상품(Product) ====================
    - 판매 기간 안 (orderable_starts_at <= now <= orderable_ends_at)
    - 재고 충분 (mode 별 cart 누적 / +1 / 무시 분기)
    - 인당 최대 구매 수량 안 (mode 별)
    - 후원 금액 정책: donation_allowed + [min, max] 범위
    - 총 금액 (product + donation + option additional) 이 [1원, 100만원)

    ==================== 상품군 (Tag) ====================
    - TagOrderableCheckSerializer 위임 (재고 / 인당 한도)

    ==================== 옵션 그룹 (OptionGroup) ====================
    - effective_visible / effective_orderable 기간 안 (그룹 값 → product fallback)
    - min/max_quantity_per_product 안
    - group 단위 max_quantity_per_user 안

    ==================== 옵션 (Option) ====================
    - 단건 정합성 — OptionOrderableCheckSerializer 가 entry 마다 검사 (SOLDOUT / 그룹 소속 / custom_response).
    - 같은 OPR 안 합산 stock / max_per_user — `_validate_aggregated_option_counts` 가 mode 별로 검사.
    """

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(deleted_at__isnull=True),
        required=True,
        allow_null=False,
    )
    options = OptionOrderableCheckSerializer(many=True, required=True, allow_empty=True, allow_null=False)
    donation_price = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        model = OrderProductRelation
        list_serializer_class = InstanceListSerializer
        fields = ("product", "options", "donation_price")

    @functools.cached_property
    def validation_mode(self) -> OrderableCheckSerializerMode:
        if not (mode := self.context.get("mode")):
            return OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART
        return mode

    @functools.cached_property
    def request(self) -> request.Request:
        return typing.cast(request.Request, self.context["request"])

    @functools.cached_property
    def user(self) -> UserExt:
        if not isinstance(self.request.user, UserExt):
            raise serializers.ValidationError(SignInErrorMessages.USER_NOT_SIGNED_IN)

        return self.request.user

    def validate_product(self, product: Product) -> Product:
        # 판매 시작일 & 판매 종료일 사이가 아닌 경우 주문 불가능
        now = now_aware()
        if not (product.orderable_starts_at <= now <= product.orderable_ends_at):
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(product.name))

        if product.leftover_stock is not None:
            # 상품의 재고가 없는 경우 주문 불가능
            if product.leftover_stock <= 0:
                raise serializers.ValidationError(ProductNotOrderableErrorMessages.SOLDOUT.format(product.name))

            # 고객이 상품의 재고를 초과하여 상품을 장바구니에 담으면 주문 불가능
            user_product_cart_included_count = product.get_user_taken_stock_count(
                user=self.user,
                include_cart=True,
                include_purchased=False,
            )
            match self.validation_mode:
                case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                    user_product_cart_included_count += 1
                case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                    # 이미 재고 체크를 위에서 했으므로, 단일 주문의 경우 확인할 필요가 없습니다.
                    user_product_cart_included_count = 0
                case OrderableCheckSerializerMode.CHECKOUT_CART:
                    pass
                case _:  # pragma: no cover
                    raise ValueError("Invalid validation mode")

            if user_product_cart_included_count > product.leftover_stock:
                raise serializers.ValidationError(
                    ProductNotOrderableErrorMessages.TOO_MUCH_CART_PRODUCT.format(product.name)
                )

        # 상품의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 담거나 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
        if product.max_quantity_per_user > 0:  # 0 = 무제한 sentinel
            match self.validation_mode:
                case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                    user_product_taken_count = (
                        product.get_user_taken_stock_count(
                            user=self.user,
                            include_cart=True,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                    user_product_taken_count = (
                        product.get_user_taken_stock_count(
                            user=self.user,
                            include_cart=False,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_CART:
                    user_product_taken_count = product.get_user_taken_stock_count(
                        user=self.user,
                        include_cart=True,
                        include_purchased=True,
                    )
                case _:  # pragma: no cover
                    raise ValueError("Invalid validation mode")

            if user_product_taken_count > product.max_quantity_per_user:
                raise serializers.ValidationError(
                    ProductNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(product.name)
                )

        # 상품군이 주문 불가능한 경우 주문 불가능
        tags = [tag_rel.tag for tag_rel in product.tags.select_related("tag").all()]
        TagOrderableCheckSerializer(
            instance=tags,
            data=[{} for _ in tags],
            context=self.context,
            many=True,
            partial=True,
        ).is_valid(raise_exception=True)

        return product

    def validate(
        self, data: ProductOrderableCheckBeforeValidationDataType
    ) -> ProductOrderableCheckAfterValidationDataType:
        product: Product = data["product"]
        options: list[OptionOrderableCheckTypedDict] = data["options"]
        donation_price: int = data.get("donation_price", 0)

        if any(o["product_option_group"].product != product for o in options):
            raise serializers.ValidationError(
                OptionGroupNotOrderableErrorMessages.OPTION_NOT_MATCH_PRODUCT.format(product.name)
            )

        for group in product.option_groups.all():
            option_selected_count = len([o for o in options if o["product_option_group"] == group])
            # 그룹 단위 visible/orderable 기간 밖이면 거절 — visible 미래/과거인 그룹은 API 노출도 안 되지만
            # 직접 ID 로 주문 시도 차단을 위해 cart validation 에서도 함께 검사한다.
            if option_selected_count > 0 and (not group.is_visible_now() or not group.is_orderable_now()):
                msg = OptionGroupNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(product.name, group.name)
                raise serializers.ValidationError(msg)
            # 옵션의 필수 선택 수량이 충족되지 않은 경우 주문 불가능
            if group.min_quantity_per_product and group.min_quantity_per_product > option_selected_count:
                msg = OptionGroupNotOrderableErrorMessages.NOT_ENOUGH_OPTION.format(product.name, group.name)
                raise serializers.ValidationError(msg)
            # 옵션의 최대 선택 수량을 초과한 경우 주문 불가능
            if group.max_quantity_per_product and option_selected_count > group.max_quantity_per_product:
                msg = OptionGroupNotOrderableErrorMessages.TOO_MUCH_OPTION.format(product.name, group.name)
                raise serializers.ValidationError(msg)
            # 옵션 그룹 단위 인당 최대 선택 수량 초과 검증 — option-level / option-counter 와 별개로 group 합산도 본다.
            if group.max_quantity_per_user > 0 and option_selected_count > 0:  # 0 = 무제한 sentinel
                match self.validation_mode:
                    case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                        total = (
                            group.get_user_taken_stock_count(user=self.user, include_cart=True, include_purchased=True)
                            + option_selected_count
                        )
                    case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                        total = (
                            group.get_user_taken_stock_count(user=self.user, include_cart=False, include_purchased=True)
                            + option_selected_count
                        )
                    case OrderableCheckSerializerMode.CHECKOUT_CART:
                        total = group.get_user_taken_stock_count(
                            user=self.user, include_cart=True, include_purchased=True
                        )
                    case _:  # pragma: no cover
                        raise ValueError("Invalid validation mode")
                if total > group.max_quantity_per_user:
                    msg = OptionGroupNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(product.name, group.name)
                    raise serializers.ValidationError(msg)

        # 같은 OPR 안 option 별 합산 stock / max_per_user 검증.
        # option-level 은 단건 SOLDOUT 만 보고 합산 검증은 모두 여기서 처리 — 단건/다건 동일 경로.
        self._validate_aggregated_option_counts(options)

        # 후원 가능 상품일 경우에만, 후원 가능 금액 범위 내에서 후원 금액을 입력받을 수 있음
        if donation_price:
            if not product.donation_allowed:
                msg = ProductNotOrderableErrorMessages.DONATION_NOT_ALLOWED.format(product.name)
                raise serializers.ValidationError(msg)
            if not (product.donation_min_price <= donation_price <= product.donation_max_price):
                msg = ProductNotOrderableErrorMessages.DONATION_PRICE_OUT_OF_RANGE.format(
                    product.name,
                    product.donation_min_price,
                    product.donation_max_price,
                )
                raise serializers.ValidationError(msg)

        total_price = (
            product.price
            + donation_price
            + sum(o["product_option"].additional_price for o in options if o["product_option"])
        )
        # 후원 금액 포함 단일 상품 금액이 0원 이하인 경우 주문 불가능 — PortOne 결제는 0원 금액에서 실패하므로 사전 차단.
        if total_price <= 0:
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.PRICE_TOO_LOW)
        # 후원 금액 포함 단일 상품 금액이 100만원 이상인 경우 주문 불가능
        if total_price >= 1_000_000:
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.PRICE_TOO_HIGH)

        return typing.cast(ProductOrderableCheckAfterValidationDataType, data | {"donation_price": donation_price})

    def _validate_aggregated_option_counts(self, options: list[OptionOrderableCheckTypedDict]) -> None:
        # 같은 OPR 안 option 별 합산 stock / max_per_user 검증. count == 1 / >= 2 동일 경로.
        # option SOLDOUT (leftover<=0) 은 option-level 이 이미 거절하므로 여기는 leftover > 0 전제 — DRF 자동 short-circuit.
        option_counter = Counter(o["product_option"] for o in options if o["product_option"])

        for option, requested_count in option_counter.items():
            product_name = option.group.product.name

            if option.leftover_stock is not None:
                total = self._aggregated_count(option, requested_count, include_purchased=False)
                if total > option.leftover_stock:
                    msg = OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(product_name, option.name)
                    raise serializers.ValidationError(msg)

            if option.max_quantity_per_user > 0:  # 0 = 무제한 sentinel
                total = self._aggregated_count(option, requested_count, include_purchased=True)
                if total > option.max_quantity_per_user:
                    msg = OptionNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(product_name, option.name)
                    raise serializers.ValidationError(msg)

    def _aggregated_count(self, option: Option, requested_count: int, *, include_purchased: bool) -> int:
        # mode 별 base count + 이번 request 의 N 합산 규칙:
        #   ADD                       — cart 누적 + N (자기 추가)
        #   CHECKOUT_SINGLE_PRODUCT   — cart 무시, purchased 만 (+ N)  / stock 검증은 purchased 도 무시 → N 만
        #   CHECKOUT_CART             — cart 누적 (이미 자기 포함, + N 없음)
        if self.validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT and not include_purchased:
            return requested_count
        base = option.get_user_taken_stock_count(
            user=self.user,
            include_cart=self.validation_mode != OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT,
            include_purchased=include_purchased,
        )
        return base + (requested_count if self.validation_mode != OrderableCheckSerializerMode.CHECKOUT_CART else 0)

    @transaction.atomic
    def create(self, validated_data: ProductOrderableCheckAfterValidationDataType) -> OrderProductRelation:
        product: Product = validated_data["product"]

        # - 만약 단일 상품을 장바구니에 담는 경우(validation_mode == ADD_SINGLE_PRODUCT_TO_CART)라면, 장바구니에 해당 상품을 담습니다.
        #   이때, 먼저 유저에 결제하지 않은 Order(장바구니)가 있는지 확인하고, 없으면 생성합니다.
        # - 단일 상품을 바로 결제하는 경우(validation_mode == CHECKOUT_SINGLE_PRODUCT)라면,
        #   먼저 OrderProductRelation을 생성 후, SingleProductCart를 생성하면서 해당 상품과 연결합니다.
        option_price = sum(
            option_group_data["product_option"].additional_price
            for option_group_data in validated_data["options"]
            if option_group_data["product_option"]
        )
        order_product_rel_create_kwargs = {
            "product": product,
            "price": product.price + option_price,
            "donation_price": validated_data.get("donation_price", 0),
        }

        if self.validation_mode == OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
            if not (cart := Order.objects.filter(user=self.user).filter_has_no_payment_histories().first()):
                cart = Order.objects.create(user=self.user)
            order_product_rel_create_kwargs["order"] = cart
        elif self.validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
            pass
        else:
            raise serializers.ValidationError(
                CriticalErrorMessages.INVALID_LOGIC.format("주문 검증 후 호출되면 안 되는 로직이 호출되었습니다.")
            )

        order_product_rel = OrderProductRelation.objects.create(**order_product_rel_create_kwargs)

        if self.validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
            SingleProductCart.objects.create(user=self.user, order_product_relation=order_product_rel)

        # 카트에 담은 상품에 대한 옵션 정보를 저장합니다.
        for option_group_data in validated_data["options"]:
            OrderProductOptionRelation.objects.create(
                order_product_relation=order_product_rel,
                product_option_group=option_group_data["product_option_group"],
                product_option=option_group_data["product_option"],
                custom_response=option_group_data["custom_response"],
            )

        return order_product_rel
