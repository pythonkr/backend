import pytest
from django.test import override_settings
from rest_framework.fields import DateTimeField
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.order.serializers.dto import OrderDto, OrderProductRelationDto
from shop.order.serializers.scancode import _OrderProductOptionRelationSerializer
from shop.product.models import Category, CategoryGroup, OptionGroup, Product

_TEST_BACKEND_DOMAIN = "https://test.pycon.kr"


@override_settings(BACKEND_DOMAIN=_TEST_BACKEND_DOMAIN)
@pytest.mark.django_db
def test_order_product_relation_dto_scancode_url_for_ticket_category(pending_order, product):
    opr = pending_order.products.first()
    assert OrderProductRelationDto(instance=opr).data == {
        "id": str(opr.id),
        "product": {"id": str(product.id), "name": product.name, "price": product.price, "image": None},
        "options": [],
        "status": opr.status,
        "price": opr.price,
        "donation_price": opr.donation_price,
        "not_refundable_reason": opr.not_refundable_reason,
        "scancode_url": f"{_TEST_BACKEND_DOMAIN}{opr.scancode_path}",
    }


@pytest.mark.django_db
def test_order_product_relation_dto_scancode_url_none_for_non_ticket_category(customer_user):
    group = CategoryGroup.objects.create(name="기타")
    category = Category.objects.create(group=group, name="굿즈")
    product = Product.objects.create(category=category, name="머그컵", price=5000)
    order = Order.objects.create(user=customer_user, name=product.name)
    opr = OrderProductRelation.objects.create(order=order, product=product, price=product.price)
    assert OrderProductRelationDto(instance=opr).data == {
        "id": str(opr.id),
        "product": {"id": str(product.id), "name": product.name, "price": product.price, "image": None},
        "options": [],
        "status": opr.status,
        "price": opr.price,
        "donation_price": opr.donation_price,
        "not_refundable_reason": opr.not_refundable_reason,
        "scancode_url": None,
    }


@override_settings(BACKEND_DOMAIN=_TEST_BACKEND_DOMAIN)
@pytest.mark.django_db
def test_order_dto_includes_scancode_url_and_nested_payload(pending_order, product):
    opr = pending_order.products.first()
    customer_info = pending_order.customer_info
    assert OrderDto(instance=pending_order).data == {
        "id": str(pending_order.id),
        "name": pending_order.name,
        "payment_histories": [],
        "products": [
            {
                "id": str(opr.id),
                "product": {"id": str(product.id), "name": product.name, "price": product.price, "image": None},
                "options": [],
                "status": opr.status,
                "price": opr.price,
                "donation_price": opr.donation_price,
                "not_refundable_reason": opr.not_refundable_reason,
                "scancode_url": f"{_TEST_BACKEND_DOMAIN}{opr.scancode_path}",
            },
        ],
        "scancode_url": f"{_TEST_BACKEND_DOMAIN}{pending_order.scancode_path}",
        "first_paid_price": pending_order.first_paid_price,
        "first_paid_at": None,
        "current_paid_price": pending_order.current_paid_price,
        "current_status": pending_order.current_status,
        "created_at": DateTimeField().to_representation(pending_order.created_at),
        "not_fully_refundable_reason": pending_order.not_fully_refundable_reason,
        "customer_info": {
            "name": customer_info.name,
            "phone": customer_info.phone,
            "email": customer_info.email,
            "organization": None,
        },
    }


@pytest.mark.django_db
def test_scancode_option_serializer_value_for_custom_response_group(completed_order, product):
    group = OptionGroup.objects.create(
        product=product, name="요청사항", is_custom_response=True, custom_response_pattern=r"^.*$"
    )
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="알레르기 있음",
    )
    assert _OrderProductOptionRelationSerializer(instance=rel).data == {"name": "요청사항", "value": "알레르기 있음"}


@pytest.mark.django_db
def test_scancode_option_serializer_value_for_custom_response_when_blank(completed_order, product):
    group = OptionGroup.objects.create(
        product=product, name="요청사항", is_custom_response=True, custom_response_pattern=r"^.*$"
    )
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="",
    )
    assert _OrderProductOptionRelationSerializer(instance=rel).data == {"name": "요청사항", "value": "-"}


@pytest.mark.django_db
def test_scancode_option_serializer_value_for_selected_option_with_additional_price(completed_order, option_group):
    option = option_group.options.create(name="L", additional_price=2000)
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=option_group,
        product_option=option,
    )
    assert _OrderProductOptionRelationSerializer(instance=rel).data == {
        "name": option_group.name,
        "value": "L (+2000원)",
    }


@pytest.mark.django_db
def test_scancode_option_serializer_value_for_selected_option_without_additional_price(
    completed_order, option_group, option
):
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=option_group,
        product_option=option,
    )
    assert _OrderProductOptionRelationSerializer(instance=rel).data == {
        "name": option_group.name,
        "value": option.name,
    }


@pytest.mark.django_db
def test_scancode_option_serializer_value_when_no_option_no_custom_response(completed_order, option_group):
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=option_group,
    )
    assert _OrderProductOptionRelationSerializer(instance=rel).data == {"name": option_group.name, "value": "-"}
