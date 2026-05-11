import collections.abc
import typing

import pandas
from rest_framework import serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.product.models import Option, OptionGroup


class ListExportSerializer(serializers.ListSerializer):
    def export(self) -> pandas.DataFrame:
        field_def = self.child.Meta.field_def  # type: ignore[attr-defined,union-attr]
        return pandas.DataFrame(data=self.data).rename(columns=dict(field_def))


class OrderExportSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email")
    customer_name = serializers.CharField(source="customer_info.name", allow_null=True)
    customer_phone = serializers.CharField(source="customer_info.phone", allow_null=True)
    customer_email = serializers.EmailField(source="customer_info.email", allow_null=True)
    customer_organization = serializers.CharField(source="customer_info.organization", allow_null=True)

    first_paid_at = serializers.DateTimeField()

    class Meta:
        model = Order
        list_serializer_class = ListExportSerializer
        field_def: collections.abc.Sequence[tuple[str, str]] = (
            ("id", "주문 번호"),
            ("user_email", "주문 계정 이메일"),
            ("customer_name", "고객명"),
            ("customer_phone", "고객 전화번호"),
            ("customer_email", "고객 이메일"),
            ("customer_organization", "고객 소속"),
            ("name", "주문명"),
            ("first_paid_at", "첫 결제 시간"),
            ("first_paid_price", "첫 결제 금액"),
            ("current_paid_price", "현재 결제 금액"),
            ("current_status", "현재 상태"),
            ("latest_imp_id", "PortOne ID"),
        )
        fields: list[str] = [field[0] for field in field_def]
        field_names: list[str] = [field[1] for field in field_def]

    def export(self) -> pandas.DataFrame:
        raise NotImplementedError(".export method is implemented in ListExportSerializer")


class OrderProductExportSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = OrderProductRelation
        field_def: collections.abc.Sequence[tuple[str, str]] = (
            ("order_id", "주문 번호"),
            ("product_id", "상품 ID"),
            ("product_name", "상품명"),
            ("status", "상태"),
            ("price", "결제 금액"),
            ("donation_price", "추가 기부액"),
        )
        list_serializer_class = ListExportSerializer
        fields: list[str] = [field[0] for field in field_def]
        field_names: list[str] = [field[1] for field in field_def]

    def to_representation(self, instance: OrderProductRelation) -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = super().to_representation(instance)

        options: collections.abc.Iterable[OrderProductOptionRelation] = instance.options.all()
        for option in options:
            option_group: OptionGroup = option.product_option_group
            selected_option: Option = option.product_option

            name: str = option_group.name
            value: str | None = option.custom_response if option_group.is_custom_response else selected_option.name
            result[name] = value

        return result

    def export(self) -> pandas.DataFrame:
        raise NotImplementedError(".export method is implemented in ListExportSerializer")
