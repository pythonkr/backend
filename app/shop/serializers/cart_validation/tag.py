import functools
import typing

from core.const.shop_error_messages import SignInErrorMessages, TagNotOrderableErrorMessages
from core.serializer.nested_model_serializer import InstanceListSerializer
from rest_framework import request, serializers
from shop.product.models import Tag
from shop.serializers.cart_validation._base import OrderableCheckSerializerMode
from user.models import UserExt


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

        if tag.max_quantity_per_user > 0:  # 0 = 무제한 sentinel
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
