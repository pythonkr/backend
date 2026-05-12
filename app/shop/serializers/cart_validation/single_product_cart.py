import functools
import typing

from django.db import transaction
from shop.order.models import CustomerInfo, OrderProductRelation
from shop.serializers.cart_validation._base import CustomerInfoCheckSerializer, OrderableCheckSerializerMode
from shop.serializers.cart_validation.product import (
    ProductOrderableCheckAfterValidationDataType,
    ProductOrderableCheckSerializer,
)


class CustomerInfoType(typing.TypedDict):
    name: str
    phone: str
    email: str
    organization: str


class SingleProductCartOrderableCheckDataType(ProductOrderableCheckAfterValidationDataType):
    customer_info: CustomerInfoType


class SingleProductCartOrderableCheckSerializer(ProductOrderableCheckSerializer):
    customer_info = CustomerInfoCheckSerializer(required=True)

    class Meta(ProductOrderableCheckSerializer.Meta):
        fields = ProductOrderableCheckSerializer.Meta.fields + ("customer_info",)  # type: ignore[assignment]

    @functools.cached_property
    def validation_mode(self) -> OrderableCheckSerializerMode:
        return OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT

    @transaction.atomic
    def create(  # type: ignore[override]
        self,
        validated_data: SingleProductCartOrderableCheckDataType,  # type: ignore[arg-type]
    ) -> OrderProductRelation:
        order_product_rel = super().create(validated_data)
        assert (single_product_cart := order_product_rel.single_product_cart)  # nosec: B101

        CustomerInfo.objects.create(**validated_data["customer_info"], single_product_cart=single_product_cart)

        return order_product_rel
