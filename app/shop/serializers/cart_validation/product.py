import functools
import typing

from core.const.shop_error_messages import (
    CriticalErrorMessages,
    OptionGroupNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
)
from core.serializer.nested_model_serializer import InstanceListSerializer
from core.util.dateutil import now_aware
from django.db import transaction
from rest_framework import request, serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.product.models import Product
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
    """
    장바구니에 담긴 상품이 주문 가능한지 확인합니다.
    아래 조건에 해당될 경우 주문 불가능합니다.

    ==================== 상품(Product) ====================
    - 판매 시작일 & 판매 종료일 사이가 아닌 경우 주문 불가능
    - 상품의 재고가 없는 경우 주문 불가능
    - 상품의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
    - 고객이 상품의 재고를 초과하여 상품을 장바구니에 담으면 주문 불가능
    - 후원 가능 상품일 경우에만, 후원 가능 금액 범위 내에서 후원 금액을 입력받을 수 있음
    - 후원 금액 포함 단일 상품 금액이 0원 미만인 경우 주문 불가능
    - 상품이 0원이거나 0원을 별도로 허용한 경우를 제외하면, 후원 금액 포함 단일 상품 금액이 0원인 경우 주문 불가능
    - 후원 금액 포함 단일 상품 금액이 100만원 이상인 경우 주문 불가능

    ==================== 상품군 (Tag) ====================
    - 상품군이 주문 불가능한 경우 주문 불가능

    ==================== 상품 옵션 (Option) ====================
    - 상품 옵션 중 필수 옵션이 매진된 경우 주문 불가능
    - 옵션의 필수 선택 수량이 충족되지 않은 경우 주문 불가능
    - 옵션의 최대 선택 수량을 초과한 경우 주문 불가능
    - 선택한 상품 옵션들 중 주문 불가능한 옵션이 있는 경우 주문 불가능
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
            # 옵션의 필수 선택 수량이 충족되지 않은 경우 주문 불가능
            if group.min_quantity_per_product and group.min_quantity_per_product > option_selected_count:
                raise serializers.ValidationError(
                    OptionGroupNotOrderableErrorMessages.NOT_ENOUGH_OPTION.format(product.name, group.name)
                )
            # 옵션의 최대 선택 수량을 초과한 경우 주문 불가능
            if group.max_quantity_per_product and option_selected_count > group.max_quantity_per_product:
                raise serializers.ValidationError(
                    OptionGroupNotOrderableErrorMessages.TOO_MUCH_OPTION.format(product.name, group.name)
                )

        # 후원 가능 상품일 경우에만, 후원 가능 금액 범위 내에서 후원 금액을 입력받을 수 있음
        if donation_price:
            if not product.donation_allowed:
                raise serializers.ValidationError(
                    ProductNotOrderableErrorMessages.DONATION_NOT_ALLOWED.format(product.name)
                )
            if not (product.donation_min_price <= donation_price <= product.donation_max_price):
                raise serializers.ValidationError(
                    ProductNotOrderableErrorMessages.DONATION_PRICE_OUT_OF_RANGE.format(
                        product.name,
                        product.donation_min_price,
                        product.donation_max_price,
                    )
                )

        # 후원 금액 포함 단일 상품 금액이 0원 미만인 경우 주문 불가능
        total_price = (
            product.price
            + donation_price
            + sum(o["product_option"].additional_price for o in options if o["product_option"])
        )
        # 후원 금액 포함 단일 상품 금액이 100만원 이상인 경우 주문 불가능
        if total_price >= 1_000_000:
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.PRICE_TOO_HIGH)

        return typing.cast(ProductOrderableCheckAfterValidationDataType, data | {"donation_price": donation_price})

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
