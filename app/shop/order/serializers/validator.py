from __future__ import annotations

import re
import typing

from core.const.shop_error_messages import OptionGroupNotModifiableErrorMessages
from core.util.dateutil import now_aware
from rest_framework import serializers
from shop.order.models import OrderProductOptionRelation, OrderProductRelation
from shop.product.models import OptionGroup


class OptionProductOptionCustomResponseModifyRequestSerializer(serializers.Serializer):
    order_product_option_relation = serializers.PrimaryKeyRelatedField(
        queryset=OrderProductOptionRelation.objects.filter_active().filter(
            order_product_relation__deleted_at__isnull=True,
            order_product_relation__status=OrderProductRelation.OrderProductStatus.paid,
            product_option_group__is_custom_response=True,
        ),
        required=True,
        allow_null=False,
    )
    custom_response = serializers.CharField(required=True)

    def validate(self, data: dict[str, str]) -> dict[str, str]:
        data = super().validate(data)
        order_product_rel = typing.cast(OrderProductRelation, self.context["order_product_rel"])
        order_product_option_relation = typing.cast(OrderProductOptionRelation, data["order_product_option_relation"])
        product_option_group: OptionGroup = order_product_option_relation.product_option_group
        custom_response = data["custom_response"]

        if order_product_option_relation.order_product_relation != order_product_rel:
            raise serializers.ValidationError(
                OptionGroupNotModifiableErrorMessages.ORDER_PRODUCT_OPTION_RELATION_MISMATCH
            )

        if not product_option_group.response_modifiable_ends_at:
            raise serializers.ValidationError(OptionGroupNotModifiableErrorMessages.RESPONSE_NOT_MODIFIABLE)

        if product_option_group.response_modifiable_ends_at < now_aware():
            raise serializers.ValidationError(OptionGroupNotModifiableErrorMessages.RESPONSE_MODIFIABLE_ENDS_AT)

        if product_option_group.custom_response_pattern and not re.match(
            product_option_group.custom_response_pattern, custom_response
        ):
            raise serializers.ValidationError(OptionGroupNotModifiableErrorMessages.CUSTOM_RESPONSE_PATTERN_MISMATCH)

        return data

    def save(self) -> OrderProductOptionRelation:  # type: ignore[override]
        data = self.validated_data
        order_product_option_relation: OrderProductOptionRelation = data["order_product_option_relation"]
        order_product_option_relation.custom_response = data["custom_response"]
        order_product_option_relation.save()
        return order_product_option_relation
