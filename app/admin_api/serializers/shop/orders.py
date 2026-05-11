from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory
from shop.product.models import Product
from user.models import UserExt


class OrderAdminSerializer(
    ReadOnlyModelSerializer,
    BaseAbstractSerializer,
    JsonSchemaSerializer,
    serializers.ModelSerializer,
):
    class SimpleUserSerializer(serializers.ModelSerializer):
        class Meta:
            model = UserExt
            read_only_fields = fields = ("id", "username", "email", "unique_id")

    class SimpleCustomerInfoSerializer(serializers.ModelSerializer):
        class Meta:
            model = CustomerInfo
            read_only_fields = fields = ("name", "phone", "email", "organization")

    class SimplePaymentHistorySerializer(serializers.ModelSerializer):
        class Meta:
            model = PaymentHistory
            read_only_fields = fields = ("id", "imp_id", "status", "price", "created_at")

    class SimpleOrderProductRelationSerializer(serializers.ModelSerializer):
        class SimpleProductSerializer(serializers.ModelSerializer):
            class Meta:
                model = Product
                read_only_fields = fields = ("id", "name_ko", "name_en", "price")

        class SimpleOrderProductOptionRelationSerializer(serializers.ModelSerializer):
            option_group_name_ko = serializers.CharField(source="product_option_group.name_ko", read_only=True)
            option_group_name_en = serializers.CharField(source="product_option_group.name_en", read_only=True)
            option_name_ko = serializers.CharField(source="product_option.name_ko", read_only=True, allow_null=True)
            option_name_en = serializers.CharField(source="product_option.name_en", read_only=True, allow_null=True)

            class Meta:
                model = OrderProductOptionRelation
                read_only_fields = fields = (
                    "id",
                    "option_group_name_ko",
                    "option_group_name_en",
                    "option_name_ko",
                    "option_name_en",
                    "custom_response",
                )

        product = SimpleProductSerializer(read_only=True)
        options = SimpleOrderProductOptionRelationSerializer(many=True, read_only=True)

        class Meta:
            model = OrderProductRelation
            fields = ("id", "product", "status", "price", "donation_price", "options")
            read_only_fields = ("id", "product", "price", "donation_price", "options")

    user = SimpleUserSerializer(read_only=True)
    customer_info = SimpleCustomerInfoSerializer(read_only=True)
    products = SimpleOrderProductRelationSerializer(many=True, read_only=True)
    payment_histories = SimplePaymentHistorySerializer(many=True, read_only=True)
    first_paid_price = serializers.IntegerField(read_only=True)
    current_paid_price = serializers.IntegerField(read_only=True)
    current_status = serializers.CharField(read_only=True)
    first_paid_at = serializers.DateTimeField(read_only=True)
    latest_imp_id = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = COMMON_ADMIN_FIELDS + (
            "name_ko",
            "name_en",
            "user",
            "customer_info",
            "products",
            "payment_histories",
            "first_paid_price",
            "current_paid_price",
            "current_status",
            "first_paid_at",
            "latest_imp_id",
        )


class OrderExportRequestSerializer(JsonSchemaSerializer, serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.UUIDField(), required=True, min_length=1)
    include_refunded = serializers.BooleanField(default=False)
