import datetime
import enum
import functools
import re
import typing
import uuid

from core.const.regex import ALLOW_ALL_PATTERN, PHONE_PATTERN
from core.const.shop_error_messages import (
    CartNotOrderableErrorMessages,
    CriticalErrorMessages,
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
    TagNotOrderableErrorMessages,
)
from core.serializer.nested_model_serializer import InstanceListSerializer
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from rest_framework import request, serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistoryStatus
from shop.product.models import Option, OptionGroup, Product, Tag
from user.models import UserExt


class CustomerInfoCheckSerializer(serializers.ModelSerializer):
    """고객 정보가 Regex에 맞는지 확인합니다."""

    name = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=False)
    phone = serializers.RegexField(PHONE_PATTERN, required=True, allow_null=False, allow_blank=False)
    email = serializers.EmailField(required=True, allow_null=False, allow_blank=False)
    organization = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=True)

    class Meta:
        model = CustomerInfo
        fields = ("name", "phone", "email", "organization")


class OrderableCheckSerializerMode(str, enum.Enum):
    ADD_SINGLE_PRODUCT_TO_CART = enum.auto()
    CHECKOUT_SINGLE_PRODUCT = enum.auto()
    CHECKOUT_CART = enum.auto()


class TagOrderableCheckSerializer(serializers.ModelSerializer):
    """
    태그가 주문 가능한지 확인합니다.
    아래 조건에 해당될 경우 주문 불가능합니다.
    - 태그의 재고가 없는 경우 주문 불가능
    - 태그의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
    """

    class Meta:
        model = Tag
        list_serializer_class = InstanceListSerializer
        fields = "__all__"

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

    def validate(self, data: dict) -> dict:
        tag = typing.cast(Tag, self.instance)
        if tag.leftover_stock is not None and tag.leftover_stock <= 0:
            raise serializers.ValidationError(TagNotOrderableErrorMessages.SOLDOUT.format(tag.name))

        if tag.max_quantity_per_user:
            match self.validation_mode:
                case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                    user_tagproduct_taken_count = (
                        tag.get_user_taken_stock_count(
                            user=self.user,
                            include_cart=True,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                    user_tagproduct_taken_count = (
                        tag.get_user_taken_stock_count(
                            user=self.user,
                            include_cart=False,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_CART:
                    user_tagproduct_taken_count = tag.get_user_taken_stock_count(
                        user=self.user,
                        include_cart=True,
                        include_purchased=True,
                    )
                case _:
                    raise ValueError("Invalid validation mode")

            if user_tagproduct_taken_count > tag.max_quantity_per_user:
                raise serializers.ValidationError(
                    TagNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH_RELATED_PRODUCTS.format(tag.name)
                )

        return data


class OptionOrderableCheckTypedDict(typing.TypedDict):
    product_option_group: OptionGroup
    product_option: Option | None
    custom_response: str | None


class OptionOrderableCheckSerializer(serializers.Serializer):
    """
    장바구니에 담긴 상품의 옵션이 주문 가능한지 확인합니다.
    아래 조건에 해당될 경우 주문 불가능합니다.

    ==================== 상품 옵션 그룹 (OptionGroup) ====================
    - 상품 옵션 중 필수 옵션이 매진된 경우 주문 불가능
    - 옵션 그룹이 custom_response를 받는 경우, custom_response가 올바른 형식으로 입력되지 않은 경우 주문 불가능
    - 옵션 그룹이 custom_response를 받지 않는 경우, option이 선택되지 않았거나 옵션 그룹에 속하지 않은 경우 주문 불가능

    ==================== 상품 옵션 (Option) ====================
    - 옵션의 재고가 없는 경우 주문 불가능
    - 옵션의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
    - 고객이 옵션의 재고를 초과하여 옵션을 장바구니에 담으면 주문 불가능
    """

    product_option_group = serializers.PrimaryKeyRelatedField(
        queryset=OptionGroup.objects.filter(deleted_at__isnull=True),
        required=True,
        allow_null=False,
    )
    product_option = serializers.PrimaryKeyRelatedField(
        queryset=Option.objects.filter(deleted_at__isnull=True),
        required=True,
        allow_null=True,
    )
    custom_response = serializers.CharField(required=True, allow_null=True, allow_blank=True)

    class Meta:
        list_serializer_class = InstanceListSerializer
        fields = "__all__"

    @property
    def validation_mode(self) -> OrderableCheckSerializerMode:
        if not (mode := self.context.get("mode")):
            return OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART
        return mode

    @property
    def group(self) -> OptionGroup | None:
        group: OptionGroup | str | uuid.UUID | None = self.initial_data.get("product_option_group")
        if not group:
            return None
        if isinstance(group, (str, uuid.UUID)):
            return OptionGroup.objects.filter(pk=group).first()
        return group

    def validate_product_option_group(self, group: OptionGroup) -> OptionGroup:
        # 상품 옵션 중 필수 옵션이 매진된 경우 주문 불가능
        if not group.is_group_stock_available():
            raise serializers.ValidationError(
                OptionGroupNotOrderableErrorMessages.SOLDOUT.format(group.product.name, group.name)
            )

        return group

    def validate_product_option(self, option: Option | None) -> Option | None:
        user: UserExt | AnonymousUser = typing.cast(request.Request, self.context["request"]).user
        if not isinstance(user, UserExt):
            raise serializers.ValidationError(SignInErrorMessages.USER_NOT_SIGNED_IN)

        if not self.group or self.group.is_custom_response:
            return None

        # 옵션 그룹이 custom_response를 받지 않는 경우, option이 선택되지 않았거나 옵션 그룹에 속하지 않은 경우 주문 불가능
        if not (option and option.group_id == self.group.id):
            raise serializers.ValidationError(OptionGroupNotOrderableErrorMessages.OPTION_NOT_SELECTED)

        product: Product = option.group.product
        if option.leftover_stock is not None:
            # 옵션의 재고가 없는 경우 주문 불가능
            if option.leftover_stock <= 0:
                raise serializers.ValidationError(
                    OptionNotOrderableErrorMessages.SOLDOUT.format(product.name, option.name)
                )

            # 고객이 옵션의 재고를 초과하여 옵션을 장바구니에 담으면 주문 불가능
            user_option_cart_included_count = option.get_user_taken_stock_count(
                user=user,
                include_cart=True,
                include_purchased=False,
            )
            match self.validation_mode:
                case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                    user_option_cart_included_count += 1
                case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                    # 이미 재고 체크를 위에서 했으므로, 단일 주문의 경우 확인할 필요가 없습니다.
                    user_option_cart_included_count = 0
                case OrderableCheckSerializerMode.CHECKOUT_CART:
                    pass
                case _:
                    raise ValueError("Invalid validation mode")

            if user_option_cart_included_count > option.leftover_stock:
                raise serializers.ValidationError(
                    OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(product.name, option.name)
                )

        # 옵션의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
        if option.max_quantity_per_user:
            match self.validation_mode:
                case OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART:
                    user_option_taken_count = (
                        option.get_user_taken_stock_count(
                            user=user,
                            include_cart=True,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT:
                    user_option_taken_count = (
                        option.get_user_taken_stock_count(
                            user=user,
                            include_cart=False,
                            include_purchased=True,
                        )
                        + 1
                    )
                case OrderableCheckSerializerMode.CHECKOUT_CART:
                    user_option_taken_count = option.get_user_taken_stock_count(
                        user=user,
                        include_cart=True,
                        include_purchased=True,
                    )
                case _:
                    raise ValueError("Invalid validation mode")

            if user_option_taken_count > option.max_quantity_per_user:
                raise serializers.ValidationError(
                    OptionNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(product.name, option.name)
                )

        return option

    def validate_custom_response(self, custom_response: str | None) -> str | None:
        if not (self.group and self.group.is_custom_response):
            return None

        # 옵션 그룹이 custom_response를 받는 경우, custom_response가 올바른 형식으로 입력되지 않은 경우 주문 불가능
        if self.group.custom_response_pattern and not re.match(self.group.custom_response_pattern, custom_response):
            raise serializers.ValidationError(OptionGroupNotOrderableErrorMessages.CUSTOM_RESPONSE_PATTERN_MISMATCH)

        return custom_response


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

    @property
    def is_free_product_allowed(self) -> bool:
        return self.context.get("is_free_product_allowed", False)

    def validate_product(self, product: Product) -> Product:
        # 판매 시작일 & 판매 종료일 사이가 아닌 경우 주문 불가능
        now = datetime.datetime.now().astimezone()
        if not (product.orderable_starts_at < now < product.orderable_ends_at):
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
                case _:
                    raise ValueError("Invalid validation mode")

            if user_product_cart_included_count > product.leftover_stock:
                raise serializers.ValidationError(
                    ProductNotOrderableErrorMessages.TOO_MUCH_CART_PRODUCT.format(product.name)
                )

        # 상품의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 담거나 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
        if product.max_quantity_per_user:
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
                case _:
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
        if total_price < 0:
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.PRICE_IS_MINUS)

        # 상품이 0원이거나 0원을 별도로 허용한 경우를 제외하면, 후원 금액 포함 단일 상품 금액이 0원인 경우 주문 불가능
        elif not (self.is_free_product_allowed or product.price == 0) and total_price == 0:
            raise serializers.ValidationError(ProductNotOrderableErrorMessages.PRICE_TOO_LOW)

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


class CustomerInfoType(typing.TypedDict):
    name: str
    phone: str
    email: str
    organization: str


class SingleProductCartOrderableCheckDataType(ProductOrderableCheckAfterValidationDataType):
    customer_info: CustomerInfoType


class SingleProductCartOrderableCheckSerializer(ProductOrderableCheckSerializer):
    customer_info = CustomerInfoCheckSerializer(required=True)

    class Meta(ProductOrderableCheckSerializer.Meta):
        fields = ProductOrderableCheckSerializer.Meta.fields + ("customer_info",)  # type: ignore[assignment]

    @functools.cached_property
    def validation_mode(self) -> OrderableCheckSerializerMode:
        return OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT

    @transaction.atomic
    def create(  # type: ignore[override]
        self,
        validated_data: SingleProductCartOrderableCheckDataType,  # type: ignore[arg-type]
    ) -> OrderProductRelation:
        order_product_rel = super().create(validated_data)
        assert (single_product_cart := order_product_rel.single_product_cart)  # nosec: B101

        # 단일 상품 장바구니에 고객 정보를 저장합니다.
        if customer_info := CustomerInfo.objects.filter(single_product_cart=single_product_cart).first():
            customer_info_serializer = CustomerInfoCheckSerializer(
                instance=customer_info, data=validated_data["customer_info"]
            )
            customer_info_serializer.is_valid(raise_exception=True)
            customer_info_serializer.save()
        else:
            CustomerInfo.objects.create(**validated_data["customer_info"], single_product_cart=single_product_cart)

        return order_product_rel


class CartOrderableCheckSerializer(serializers.Serializer):
    """
    장바구니가 주문 가능한지 확인합니다.
    아래 조건에 해당될 경우 주문 불가능합니다.
    - 이미 결제한 장바구니인 경우 주문 불가능
    - 장바구니 내에 이미 결제한 상품이 있는 경우 주문 불가능
    - 장바구니 내의 상품들 주문 금액 합계가 0원 미만이거나 100만원 이상인 경우 주문 불가능
    """

    cart = serializers.PrimaryKeyRelatedField(queryset=Order.objects.filter_has_no_payment_histories(), required=True)

    class Meta:
        fields = ("cart",)

    def validate(self, data: dict) -> dict:
        cart: Order = data["cart"]

        # 이미 결제한 장바구니인 경우 주문 불가능
        if cart.current_status != PaymentHistoryStatus.pending or cart.payment_histories.exists():
            raise serializers.ValidationError(CartNotOrderableErrorMessages.ALREADY_ORDERED)

        # 장바구니 내에 이미 결제한 상품이 있는 경우 주문 불가능
        if cart.products.exclude(status=OrderProductRelation.OrderProductStatus.pending).exists():
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CONTAINS_PAID_PRODUCT)

        # 장바구니 내의 상품들 주문 금액 합계가 0원 이하거나 100만원 이상인 경우 주문 불가능
        if 0 > cart.first_paid_price:
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CART_PRICE_TOO_LOW)
        if cart.first_paid_price >= 1_000_000:
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CART_PRICE_TOO_HIGH)

        return data
