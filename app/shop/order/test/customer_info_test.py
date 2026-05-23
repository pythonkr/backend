import pytest
from django.db import IntegrityError
from shop.order.models import CustomerInfo, Order


@pytest.mark.django_db
def test_customer_info_one_to_one_with_order_rejects_duplicate(order_factory):
    pending_order = order_factory()
    with pytest.raises(IntegrityError):
        CustomerInfo.objects.create(order=pending_order, name="동명이인", phone="01000000000", email="a@a.a")


@pytest.mark.django_db
def test_customer_info_one_to_one_with_single_product_cart_rejects_duplicate(single_product_cart):
    with pytest.raises(IntegrityError):
        CustomerInfo.objects.create(
            single_product_cart=single_product_cart, name="동명이인", phone="01000000000", email="a@a.a"
        )


@pytest.mark.django_db
def test_customer_info_can_be_orphan_without_order_or_cart():
    # 두 FK 모두 null=True — orphan CustomerInfo 가 DB 차원에서는 허용됨 (model invariant 미강제).
    info = CustomerInfo.objects.create(name="orphan", phone="01000000000", email="a@a.a")
    assert info.order_id is None
    assert info.single_product_cart_id is None


@pytest.mark.django_db
def test_customer_info_optional_organization_defaults_to_none(customer_user):
    order = Order.objects.create(user=customer_user, name="x")
    info = CustomerInfo.objects.create(order=order, name="홍길동", phone="01000000000", email="a@a.a")
    assert info.organization is None
