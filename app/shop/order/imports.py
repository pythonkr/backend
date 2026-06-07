import dataclasses
import functools
import types
import typing
import uuid

import pandas
from core.const.regex import ALLOW_ALL_PATTERN, PHONE_PATTERN
from django.db import transaction
from django.db.models import Prefetch
from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, TicketInfo
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Option, OptionGroup, Product
from shop.serializers.cart_validation import OrderableCheckSerializerMode, ProductOrderableCheckSerializer
from user.models import UserExt

OPTION_GROUP_PREFETCH = "_prefetched_all_option_groups"
CUSTOMER_INFO_FIELDS = ("name", "phone", "email", "organization")


class SerializerDataOptions(typing.TypedDict):
    product_option_group: uuid.UUID | str
    product_option: uuid.UUID | str | None
    custom_response: str | None


@dataclasses.dataclass
class OptionInputData:
    option_group: OptionGroup
    option: Option | None
    custom_response: str | None

    @functools.cached_property
    def resp_mode(self) -> bool:
        return self.option_group.is_custom_response or not self.option

    def to_dict(self) -> SerializerDataOptions:
        return SerializerDataOptions(
            product_option_group=self.option_group.id,
            product_option=self.option.id if not self.resp_mode else None,
            custom_response=self.custom_response if self.resp_mode else None,
        )


class OrderProductImportSerializer(serializers.ModelSerializer):
    name = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=False)
    phone = serializers.RegexField(PHONE_PATTERN, required=True, allow_null=False, allow_blank=False)
    email = serializers.EmailField(required=True, allow_null=False, allow_blank=False)
    organization = serializers.RegexField(ALLOW_ALL_PATTERN, required=True, allow_null=False, allow_blank=True)

    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter_active(), source="id")
    donation_price = serializers.IntegerField(required=True)
    options = serializers.DictField(child=serializers.CharField(), required=True)

    class Meta:
        model = OrderProductRelation
        fields_without_options: list[str] = ["name", "phone", "email", "organization", "product_id", "donation_price"]
        fields: list[str] = fields_without_options + ["options"]

    @classmethod
    def get_template_csv(cls, product: Product) -> str:
        serializer_fields: list[str] = cls.Meta.fields_without_options
        option_fields: list[str] = list(group.name for group in product.option_groups.filter_active())
        return pandas.DataFrame(columns=serializer_fields + option_fields).to_csv(index=False)

    @functools.cached_property
    def user(self) -> UserExt | None:
        return UserExt.objects.filter(email=self.initial_data.get("email", "")).first()

    @functools.cached_property
    def product(self) -> Product | None:
        prod_id = self.initial_data.get("product_id", "")
        prefetch = Prefetch(
            lookup="option_groups",
            queryset=OptionGroup.objects.filter_active().prefetch_related(
                Prefetch("options", queryset=Option.objects.filter_active())
            ),
            to_attr=OPTION_GROUP_PREFETCH,
        )
        return Product.objects.filter_active().prefetch_related(prefetch).filter(id=prod_id).first()

    @functools.cached_property
    def option_input_data(self) -> list[OptionInputData]:
        if not self.product:
            return []

        input_options: dict[str, str] = {k: v for k, v in self.initial_data.items() if k not in self.Meta.fields}
        result: list[OptionInputData] = []
        groups: list[OptionGroup] = list(
            getattr(self.product, OPTION_GROUP_PREFETCH, None) or self.product.option_groups.filter_active()
        )
        for group in groups:
            if not (value := input_options.get(group.name)):
                continue

            if group.is_custom_response:
                result.append(OptionInputData(option_group=group, option=None, custom_response=value))
                continue

            if not (option := Option.objects.filter_active().filter(group=group, name=value).first()):
                raise serializers.ValidationError(detail=f"Invalid option: '{group.name}' - {value}")

            result.append(OptionInputData(option_group=group, option=option, custom_response=None))

        return result

    def to_internal_value(self, data: dict[str, str]) -> dict[str, typing.Any]:
        serializer_fields: list[str] = self.Meta.fields_without_options
        option_fields: list[str] = [name for name in data.keys() if name not in serializer_fields]

        options: dict[str, str] = {name: data[name] for name in option_fields}
        return super().to_internal_value(data | {"options": options})

    def validate(self, data: dict) -> dict:
        if not self.user:
            raise serializers.ValidationError("User does not exists")

        check_data = {
            "product": self.product.id,
            "donation_price": data["donation_price"],
            "options": [d.to_dict() for d in self.option_input_data],
        }
        if self.product.category.is_ticket:
            check_data["ticket_info"] = {field: data[field] for field in CUSTOMER_INFO_FIELDS}

        ProductOrderableCheckSerializer(
            context={
                "mode": OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT,
                "request": types.SimpleNamespace(user=self.user),
            },
            data=check_data,
        ).is_valid(raise_exception=True)
        return data

    @transaction.atomic
    def create(self, validated_data: dict[str, typing.Any]) -> OrderProductRelation:
        additional_price: int = sum(od.option.additional_price for od in self.option_input_data if not od.resp_mode)
        total_price: int = self.product.price + additional_price

        order_product: OrderProductRelation = OrderProductRelation.objects.create(
            order=Order.objects.create(user=self.user, name=self.product.name),
            product=self.product,
            status=OrderProductRelation.OrderProductStatus.paid,
            price=total_price,
            donation_price=validated_data["donation_price"],
        )
        customer_info_data = {field: validated_data[field] for field in CUSTOMER_INFO_FIELDS}
        CustomerInfo.objects.create(order=order_product.order, **customer_info_data)
        if self.product.category.is_ticket:
            TicketInfo.objects.create(order_product_relation=order_product, **customer_info_data)

        for data in self.option_input_data:
            OrderProductOptionRelation.objects.create(
                order_product_relation=order_product,
                product_option_group=data.option_group,
                product_option=data.option,
                custom_response=data.custom_response,
            )

        PaymentHistory.objects.create(
            order=order_product.order,
            imp_id=None,
            status=PaymentHistoryStatus.completed,
            price=total_price,
        )

        return order_product
