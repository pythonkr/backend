import uuid

import pytest
from shop.order.models import Order, OrderProductOptionRelation
from shop.product.models import OptionGroup


def test_merchant_uid_is_short_enough():
    assert len(Order(id=uuid.uuid4(), prepared_cart_hash="a" * 16).merchant_uid) <= 40


def test_prepared_price_returns_none_without_snapshot():
    assert Order().prepared_price is None


@pytest.mark.parametrize(
    ("snapshot", "amount"),
    [
        (None, 1000),
        ({"attempt": {"id": "x"}, "price": 1000}, None),
        ({"attempt": {"id": "x"}, "price": 1000}, "xyz"),
        ({"attempt": "not-a-dict", "price": 1000}, 1000),
    ],
)
def test_matches_payment_preparation_returns_false_for_malformed_inputs(snapshot, amount):
    order = Order(prepared_cart_snapshot=snapshot, prepared_cart_hash="a" * 16)
    assert not order.matches_payment_preparation("merchant", amount)


@pytest.mark.django_db
def test_order_product_relation_save_invalidates_pending_order_preparation(order_factory):
    order = order_factory(status="prepared")

    opr = order.products.first()
    opr.donation_price = 100
    opr.save()

    order.refresh_from_db()
    assert order.prepared_cart_snapshot is None
    assert order.prepared_cart_hash is None


@pytest.mark.django_db
def test_order_queryset_filter_by_merchant_uid_matches_id_and_hash(order_factory):
    order = order_factory(status="prepared")
    merchant_uid = order.merchant_uid

    assert list(type(order).objects.filter_by_merchant_uid(merchant_uid)) == [order]
    assert not type(order).objects.filter_by_merchant_uid("invalid").exists()
    assert not type(order).objects.filter_by_merchant_uid(1234).exists()
    assert order.matches_payment_preparation(merchant_uid, order.first_paid_price)
    assert not order.matches_payment_preparation(merchant_uid, order.first_paid_price + 0.5)

    order.delete()
    assert not type(order).objects.filter_by_merchant_uid(merchant_uid).exists()


@pytest.mark.django_db
def test_single_product_cart_queryset_filter_by_merchant_uid_matches_id_and_hash(single_product_cart):
    single_product_cart.prepare_payment()
    merchant_uid = single_product_cart.merchant_uid

    assert list(type(single_product_cart).objects.filter_by_merchant_uid(merchant_uid)) == [single_product_cart]
    assert not type(single_product_cart).objects.filter_by_merchant_uid("invalid").exists()

    single_product_cart.delete()
    assert not type(single_product_cart).objects.filter_by_merchant_uid(merchant_uid).exists()


@pytest.mark.django_db
def test_prepare_payment_stores_snapshot_and_changes_hash_for_each_attempt(order_factory):
    order = order_factory()

    order.prepare_payment()
    first_merchant_uid = order.merchant_uid
    first_hash = order.prepared_cart_hash
    first_snapshot = order.prepared_cart_snapshot

    assert len(first_hash) == 16
    assert first_snapshot["attempt"]["id"]
    assert first_snapshot["attempt"]["prepared_at"]
    assert first_snapshot["price"] == order.first_paid_price
    assert order.prepared_price == order.first_paid_price

    order.prepare_payment()

    assert order.merchant_uid != first_merchant_uid
    assert order.prepared_cart_hash != first_hash
    assert order.prepared_cart_snapshot["attempt"]["id"] != first_snapshot["attempt"]["id"]


@pytest.mark.django_db
def test_order_product_relation_save_invalidates_single_product_cart_preparation(single_product_cart):
    single_product_cart.prepare_payment()

    opr = single_product_cart.order_product_relation
    opr.donation_price = 100
    opr.save()

    single_product_cart.refresh_from_db()
    assert single_product_cart.prepared_cart_snapshot is None
    assert single_product_cart.prepared_cart_hash is None


@pytest.mark.django_db
def test_order_product_option_relation_create_update_delete_invalidates_pending_order_preparation(
    product, order_factory
):
    order = order_factory(status="prepared")
    opr = order.products.first()
    option_group = OptionGroup.objects.create(
        product=product,
        name="요청사항",
        is_custom_response=True,
        custom_response_pattern=r"^.*$",
    )

    option_rel = OrderProductOptionRelation.objects.create(
        order_product_relation=opr,
        product_option_group=option_group,
        custom_response="initial",
    )
    order.refresh_from_db()
    assert order.prepared_cart_snapshot is None
    assert order.prepared_cart_hash is None

    order.prepare_payment()
    option_rel.custom_response = "updated"
    option_rel.save()
    order.refresh_from_db()
    assert order.prepared_cart_snapshot is None
    assert order.prepared_cart_hash is None

    order.prepare_payment()
    option_rel.delete()
    order.refresh_from_db()
    assert order.prepared_cart_snapshot is None
    assert order.prepared_cart_hash is None


@pytest.mark.django_db
def test_paid_order_product_option_relation_save_does_not_clear_payment_preparation(modifiable_option_relation):
    order = modifiable_option_relation.order_product_relation.order
    order.prepare_payment()
    merchant_uid = order.merchant_uid

    modifiable_option_relation.custom_response = "updated"
    modifiable_option_relation.save()

    order.refresh_from_db()
    assert order.merchant_uid == merchant_uid
