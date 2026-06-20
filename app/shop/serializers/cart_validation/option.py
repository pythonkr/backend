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
from user.models import UserExt


class OptionOrderableCheckTypedDict(typing.TypedDict):
    product_option_group: OptionGroup
    product_option: Option | None
    custom_response: str | None


class OptionOrderableCheckSerializer(serializers.Serializer):
    """option entry 의 단건 정합성을 확인. 합산 stock / max_per_user 는 ProductOrderableCheckSerializer 가 처리.

    검사 항목:
    - 옵션 그룹 단위 SOLDOUT (필수 옵션이 매진)
    - custom_response 그룹의 패턴 일치
    - 비 custom_response 그룹에서 option 의 그룹 소속 / 선택 여부
    - 옵션 단건 SOLDOUT (leftover_stock <= 0)
    """

    product_option_group = serializers.PrimaryKeyRelatedField(
        queryset=OptionGroup.objects.filter_active(),
        required=True,
        allow_null=False,
    )
    product_option = serializers.PrimaryKeyRelatedField(
        queryset=Option.objects.filter_active(),
        required=True,
        allow_null=True,
    )
    custom_response = serializers.CharField(required=True, allow_null=True, allow_blank=True)

    class Meta:
        list_serializer_class = InstanceListSerializer
        fields = "__all__"

    @property
    def group(self) -> OptionGroup | None:
        group: OptionGroup | str | uuid.UUID | None = self.initial_data.get("product_option_group")
        if not group:
            return None
        if isinstance(group, (str, uuid.UUID)):
            return OptionGroup.objects.filter_active().filter(pk=group).first()
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

        # option 이 선택되지 않았거나 옵션 그룹에 속하지 않은 경우("선택해주세요" 상태).
        # placeholder_mode 가 OPTIONAL 일 때만 미선택을 허용하고, 그 외에는 주문 불가능.
        if not (option and option.group_id == self.group.id):
            if self.group.placeholder_mode == OptionGroup.PlaceholderMode.OPTIONAL:
                return None
            raise serializers.ValidationError(OptionGroupNotOrderableErrorMessages.OPTION_NOT_SELECTED)

        # 옵션의 재고가 없는 경우 주문 불가능 — 단건 SOLDOUT. 합산 stock / max_per_user 는 product-level 이 본다.
        if option.leftover_stock is not None and option.leftover_stock <= 0:
            product: Product = option.group.product
            raise serializers.ValidationError(OptionNotOrderableErrorMessages.SOLDOUT.format(product.name, option.name))

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
