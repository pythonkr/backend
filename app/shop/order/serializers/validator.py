from __future__ import annotations

import re
import typing

from core.const.regex import ALLOW_ALL_PATTERN, PHONE_PATTERN
from core.const.shop_error_messages import OptionGroupNotModifiableErrorMessages, ProductNotOrderableErrorMessages
from core.util.dateutil import now_aware
from django.db import transaction
from rest_framework import serializers
from shop.order.models import OrderProductOptionRelation, OrderProductRelation, TicketInfo
from shop.product.models import OptionGroup, Product


class TicketInfoSerializer(serializers.ModelSerializer):
    name = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=False)
    phone = serializers.RegexField(PHONE_PATTERN, required=True, allow_null=False, allow_blank=False)
    email = serializers.EmailField(required=True, allow_null=False, allow_blank=False)
    organization = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=True)
    contribution_message = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = TicketInfo
        fields = ("name", "phone", "email", "organization", "contribution_message")


def validate_ticket_info_against_product(product: Product, ticket_info: dict | None) -> None:
    if not ticket_info:
        return
    if not product.category.is_ticket:
        raise serializers.ValidationError(
            {"ticket_info": ProductNotOrderableErrorMessages.TICKET_INFO_NOT_ALLOWED.format(product.name)}
        )
    if ticket_info.get("contribution_message") and not product.donation_allowed:
        raise serializers.ValidationError(
            {"ticket_info": ProductNotOrderableErrorMessages.CONTRIBUTION_MESSAGE_NOT_ALLOWED.format(product.name)}
        )


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
        order_product_rel = self.context.get("order_product_rel") or self.root.instance
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


class OrderProductUpdateSerializer(serializers.Serializer):
    ticket_info = TicketInfoSerializer(required=False, write_only=True)
    options = OptionProductOptionCustomResponseModifyRequestSerializer(many=True, required=False, write_only=True)

    def validate(self, data: dict) -> dict:
        data = super().validate(data)
        validate_ticket_info_against_product(self.instance.product, data.get("ticket_info"))
        return data

    @transaction.atomic
    def update(self, instance: OrderProductRelation, validated_data: dict) -> OrderProductRelation:
        for option_data in validated_data.get("options", []):
            option_relation: OrderProductOptionRelation = option_data["order_product_option_relation"]
            option_relation.custom_response = option_data["custom_response"]
            option_relation.save()
        if ticket_info_data := validated_data.get("ticket_info"):
            TicketInfo.objects.update_or_create(order_product_relation=instance, defaults=ticket_info_data)
        return instance
