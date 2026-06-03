from urllib.parse import urljoin

from django.conf import settings
from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Option, OptionGroup, Product


class PaymentHistoryDto(serializers.ModelSerializer):
    class Meta:
        fields = ("status", "price")
        model = PaymentHistory


class SimpleProductDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "name", "price", "image")
        model = Product


class SimpleOptionDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "name", "additional_price")
        model = Option


class SimpleOptionGroupDto(serializers.ModelSerializer):
    class Meta:
        fields = (
            "id",
            "name",
            "is_custom_response",
            "custom_response_pattern",
            "response_modifiable_ends_at",
        )
        model = OptionGroup


class OrderProductOptionRelationDto(serializers.ModelSerializer):
    product_option_group = SimpleOptionGroupDto()
    product_option = SimpleOptionDto(allow_null=True)

    class Meta:
        fields = ("id", "product_option", "product_option_group", "custom_response")
        model = OrderProductOptionRelation


class OrderProductRelationDto(serializers.ModelSerializer):
    product = SimpleProductDto()
    options = OrderProductOptionRelationDto(many=True)
    scancode_url = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "id",
            "product",
            "options",
            "status",
            "price",
            "donation_price",
            "not_refundable_reason",
            "scancode_url",
        )
        model = OrderProductRelation

    def get_scancode_url(self, obj: OrderProductRelation) -> str | None:
        if not obj.product.category.is_ticket:
            return None

        return urljoin(settings.BACKEND_DOMAIN, obj.scancode_path)


class CustomerInfoDto(serializers.ModelSerializer):
    class Meta:
        fields = ("name", "phone", "email", "organization")
        model = CustomerInfo


class OrderDto(serializers.ModelSerializer):
    payment_histories = PaymentHistoryDto(many=True, source="active_payment_histories")
    products = OrderProductRelationDto(many=True, source="active_products")
    current_status = serializers.ChoiceField(choices=PaymentHistoryStatus.choices)
    scancode_url = serializers.SerializerMethodField()

    customer_info = CustomerInfoDto(allow_null=True)

    class Meta:
        fields = (
            "id",
            "name",
            "payment_histories",
            "products",
            "scancode_url",
            "first_paid_price",
            "first_paid_at",
            "current_paid_price",
            "current_status",
            "created_at",
            "not_fully_refundable_reason",
            "customer_info",
            "merchant_uid",
        )
        model = Order

    def get_scancode_url(self, obj: Order) -> str:
        return urljoin(settings.BACKEND_DOMAIN, obj.scancode_path)


class SingleProductCartDto(serializers.ModelSerializer):
    payment_histories = PaymentHistoryDto(many=True, source="active_payment_histories")
    products = OrderProductRelationDto(many=True, source="active_products")
    current_status = serializers.ChoiceField(choices=PaymentHistoryStatus.choices)

    customer_info = CustomerInfoDto(allow_null=True)

    class Meta:
        fields = (
            "id",
            "name",
            "payment_histories",
            "products",
            "first_paid_price",
            "current_paid_price",
            "current_status",
            "created_at",
            "customer_info",
            "merchant_uid",
        )
        model = SingleProductCart
