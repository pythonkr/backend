import pytest
from shop.order.models import Order, SingleProductCart


@pytest.mark.django_db
def test_queryset_delete_sets_deleted_at_without_removing_row(customer_user):
    order = Order.objects.create(user=customer_user, name="x")
    Order.objects.filter(id=order.id).delete()

    refreshed = Order.objects.get(id=order.id)
    assert refreshed.deleted_at is not None


@pytest.mark.django_db
def test_instance_delete_sets_deleted_at_and_deleted_by(customer_user):
    order = Order.objects.create(user=customer_user, name="x")
    order.delete()

    refreshed = Order.objects.get(id=order.id)
    assert refreshed.deleted_at is not None


@pytest.mark.django_db
def test_filter_active_excludes_soft_deleted_rows(customer_user):
    alive = Order.objects.create(user=customer_user, name="alive")
    soft_deleted = Order.objects.create(user=customer_user, name="ghost")
    soft_deleted.delete()

    active_ids = list(Order.objects.filter_active().values_list("id", flat=True))
    assert alive.id in active_ids
    assert soft_deleted.id not in active_ids


@pytest.mark.django_db
def test_hard_delete_removes_row_completely(customer_user):
    order = Order.objects.create(user=customer_user, name="x")
    Order.objects.filter(id=order.id).hard_delete()
    assert not Order.objects.filter(id=order.id).exists()


@pytest.mark.django_db
def test_single_product_cart_to_order_hard_deletes_cart(single_product_cart):
    # SingleProductCart 는 cart→order promote 시 hard_delete — 다른 모델은 soft delete 가 기본이라 명시적 단언.
    cart_id = single_product_cart.id
    single_product_cart.to_order()
    assert not SingleProductCart.objects.filter(id=cart_id).exists()


@pytest.mark.django_db
def test_audit_fields_default_to_none_when_no_thread_local_user(customer_user):
    # `_isolate_thread_local` autouse fixture 가 request 를 정리해 get_current_user() → None.
    order = Order.objects.create(user=customer_user, name="x")
    assert order.created_by is None
    assert order.updated_by is None
    assert order.deleted_by is None
