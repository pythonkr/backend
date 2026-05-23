import re
import typing
import uuid

from core.const.shop_error_messages import (
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
    SignInErrorMessages,
)
from core.serializer.nested_model_serializer import InstanceListSerializer
from django.contrib.auth.models import AnonymousUser
from rest_framework import request, serializers
from shop.product.models import Option, OptionGroup, Product
from shop.serializers.cart_validation._base import OrderableCheckSerializerMode
from user.models import UserExt


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
                case _:  # pragma: no cover
                    raise ValueError("Invalid validation mode")

            if user_option_cart_included_count > option.leftover_stock:
                raise serializers.ValidationError(
                    OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(product.name, option.name)
                )

        # 옵션의 최대 구매 수량이 정해져있으면, 해당 사용자가 이미 구매한 수량이 최대 구매 수량을 초과하는 경우 주문 불가능
        if option.max_quantity_per_user > 0:  # 0 = 무제한 sentinel
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
                case _:  # pragma: no cover
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
        if self.group.custom_response_pattern and not re.match(
            self.group.custom_response_pattern, custom_response or ""
        ):
            raise serializers.ValidationError(OptionGroupNotOrderableErrorMessages.CUSTOM_RESPONSE_PATTERN_MISMATCH)

        return custom_response
