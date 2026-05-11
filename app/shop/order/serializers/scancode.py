from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.product.models import Product
from user.models import UserExt


class _ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name")


class _OrderProductOptionRelationSerializer(serializers.ModelSerializer):
    """OrderProductOptionRelation → `{name, value}`. is_custom_response 분기에 따라 value 결정."""

    name = serializers.CharField(source="product_option_group.name")
    value = serializers.SerializerMethodField()

    class Meta:
        model = OrderProductOptionRelation
        fields = ("name", "value")

    def get_value(self, obj: OrderProductOptionRelation) -> str:
        if obj.product_option_group.is_custom_response:
            return obj.custom_response or "-"
        if option := obj.product_option:
            return option.name + (f" (+{option.additional_price}원)" if option.additional_price > 0 else "")
        return "-"


class _OrderProductRelationSerializer(serializers.ModelSerializer):
    """OrderProductRelation 공통 nested — product + options + 금액/상태."""

    product = _ProductSerializer()
    options = _OrderProductOptionRelationSerializer(many=True)

    class Meta:
        model = OrderProductRelation
        fields = ("product", "options", "price", "donation_price", "status")


class OrderProductScanCodeSerializer(_OrderProductRelationSerializer):
    """단일 OrderProductRelation (티켓) 의 QR 페이지용 응답 — base + id/short_id/order context."""

    class _OrderSerializer(serializers.ModelSerializer):
        class Meta:
            fields = ("id", "first_paid_at")
            model = Order

    order = _OrderSerializer()

    class Meta(_OrderProductRelationSerializer.Meta):
        fields = ("id", "short_id", "order", *_OrderProductRelationSerializer.Meta.fields)


class OrderScanCodeSerializer(serializers.ModelSerializer):
    """주문 QR 페이지 — 단일 주문 (order scancode page) + User scancode 의 order list 양쪽에서 사용."""

    class _CustomerInfoSerializer(serializers.ModelSerializer):
        class Meta:
            model = CustomerInfo
            fields = ("name", "phone", "email", "organization")

    customer_info = _CustomerInfoSerializer()
    items = _OrderProductRelationSerializer(many=True, source="products")

    class Meta:
        model = Order
        fields = (
            "id",
            "short_id",
            "name",
            "created_at",
            "first_paid_at",
            "current_status",
            "current_paid_price",
            "customer_info",
            "items",
        )


class UserScanCodeSerializer(serializers.ModelSerializer):
    """User 의 QR 페이지용 응답 — 식별 정보만. 주문 목록은 별도로 OrderScanCodeRowSerializer 사용."""

    class Meta:
        model = UserExt
        fields = ("unique_id", "short_id")
