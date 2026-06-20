import re
import typing

from core.serializer.nested_model_serializer import InstanceListSerializer, NestedModelSerializer
from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory
from shop.product.models import Option, OptionGroup, Product
from user.models import UserExt

PossibleStatusFSM: dict[OrderProductRelation.OrderProductStatus, set[OrderProductRelation.OrderProductStatus]] = {
    # 접수 데스크에서는 결제 완료나 그 이후의 상태로 변경할 수 없음
    OrderProductRelation.OrderProductStatus.pending: set(),
    OrderProductRelation.OrderProductStatus.paid: {OrderProductRelation.OrderProductStatus.used},
    OrderProductRelation.OrderProductStatus.used: {OrderProductRelation.OrderProductStatus.paid},
    # 이미 환불된 상품은 사용 또는 결제 완료로 변경할 수 없음
    OrderProductRelation.OrderProductStatus.refunded: set(),
}


class SimplePaymentHistoryDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("status", "price", "created_at")
        model = PaymentHistory


class SimpleProductDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "name", "price")
        model = Product


class SimpleOptionGroupDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "name", "is_custom_response", "custom_response_pattern", "placeholder_mode")
        model = OptionGroup


class SimpleOptionDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "name", "additional_price")
        model = Option


class SimpleOrderProductOptionRelationDeskSupportDto(NestedModelSerializer):
    id = serializers.UUIDField(required=True)
    product_option_group = SimpleOptionGroupDeskSupportDto(read_only=True)
    product_option = SimpleOptionDeskSupportDto(allow_null=True, read_only=True)
    custom_response = serializers.CharField(allow_null=False, allow_blank=True)  # Modifiable

    class Meta:
        fields = ("id", "product_option_group", "product_option", "custom_response")
        model = OrderProductOptionRelation
        list_serializer_class = InstanceListSerializer

    def validate_id(self, value: str) -> str:
        if value != typing.cast(OrderProductOptionRelation, self.instance).id:
            raise serializers.ValidationError("id must not be modified")
        return value

    def validate_custom_response(self, value: str) -> str:
        option_group: OptionGroup = typing.cast(OrderProductOptionRelation, self.instance).product_option_group
        if not option_group.is_custom_response:
            raise serializers.ValidationError("cannot set custom response to non-custom-response option group")
        if not option_group.custom_response_pattern:
            raise serializers.ValidationError("custom response pattern is not set, please contact the administrator")
        if not re.match(option_group.custom_response_pattern, value):
            raise serializers.ValidationError("custom response does not match the pattern")

        return value


class SimpleOrderProductRelationDeskSupportDto(NestedModelSerializer):
    id = serializers.UUIDField(required=True)
    price = serializers.IntegerField(read_only=True)
    donation_price = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(
        choices=OrderProductRelation.OrderProductStatus.choices,
        required=False,
    )  # Modifiable

    product = SimpleProductDeskSupportDto(read_only=True)
    options = SimpleOrderProductOptionRelationDeskSupportDto(many=True, required=False)  # Modifiable

    class Meta:
        fields = (
            "id",
            "price",
            "donation_price",
            "status",
            # Related fields
            "product",
            "options",
        )
        model = OrderProductRelation
        list_serializer_class = InstanceListSerializer

    def validate_status(
        self, value: OrderProductRelation.OrderProductStatus
    ) -> OrderProductRelation.OrderProductStatus:
        instance = typing.cast(OrderProductRelation, self.instance)
        if value == instance.status:
            return value
        if value not in PossibleStatusFSM[typing.cast(OrderProductRelation.OrderProductStatus, instance.status)]:
            raise serializers.ValidationError("해당 상태로 변경할 수 없습니다.")
        return value


class SimpleUserDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "username", "email", "unique_id")
        model = UserExt


class SimpleCustomerInfoDeskSupportDto(serializers.ModelSerializer):
    class Meta:
        fields = ("name", "email", "phone", "organization")
        model = CustomerInfo


class DeskSupportSerializer(NestedModelSerializer):
    id = serializers.UUIDField(read_only=True)
    first_paid_price = serializers.IntegerField(read_only=True)
    first_paid_at = serializers.DateTimeField(read_only=True)
    current_paid_price = serializers.IntegerField(read_only=True)
    current_status = serializers.CharField(read_only=True)

    payment_histories = SimplePaymentHistoryDeskSupportDto(many=True, read_only=True)
    products = SimpleOrderProductRelationDeskSupportDto(many=True, required=False)  # Modifiable
    user = SimpleUserDeskSupportDto(read_only=True)
    customer_info = SimpleCustomerInfoDeskSupportDto(read_only=True)

    class Meta:
        fields = (
            "id",
            "name",
            "first_paid_price",
            "first_paid_at",
            "current_paid_price",
            "current_status",
            # Related fields
            "payment_histories",
            "products",
            "user",
            "customer_info",
        )
        model = Order
