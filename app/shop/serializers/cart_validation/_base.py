import enum

from core.const.regex import ALLOW_ALL_PATTERN, PHONE_PATTERN
from rest_framework import serializers
from shop.order.models import CustomerInfo


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
