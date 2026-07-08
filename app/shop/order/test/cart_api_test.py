import threading
import time
from types import SimpleNamespace

import pytest
from core.const.shop_error_messages import ProductNotOrderableErrorMessages
from core.util.testutil import to_json
from django import db
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from rest_framework.test import APIClient
from shop.conftest import VALID_TICKET_INFO
from shop.order.models import Order, OrderProductRelation
from shop.order.serializers.dto import OrderDto
from shop.order.views.carts import CartProductViewSet
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.serializers.cart_validation import OrderableCheckSerializerMode, ProductOrderableCheckSerializer
from shop.test.helpers import CartApi, CartProductsApi


@pytest.mark.django_db
def test_cart_returns_empty_dict_when_user_has_no_cart(customer_client):
    response = CartApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_returns_order_dto_when_cart_exists(customer_client, order_factory):
    pending_order = order_factory()
    response = CartApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json(OrderDto(instance=pending_order).data)


@pytest.mark.django_db
def test_cart_excludes_other_users_cart(other_client, order_factory):
    order_factory()
    response = CartApi(http_client=other_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_returns_empty_when_request_unauthenticated(anon_client):
    response = CartApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_add_product_appends_to_existing_unpaid_cart(customer_client, customer_user, ticket_product):
    existing_cart = Order.objects.create(user=customer_user, name="cart")
    response = CartProductsApi(http_client=customer_client).create(
        {
            "product": str(ticket_product.id),
            "options": [],
            "ticket_info": VALID_TICKET_INFO,
        }
    )
    assert response.status_code == HTTP_201_CREATED
    assert OrderProductRelation.objects.filter(order=existing_cart, product=ticket_product).exists()


@pytest.mark.django_db
def test_cart_add_product_invalidates_prepared_payment(customer_client, ticket_product, order_factory):
    existing_cart = order_factory(status="prepared")

    response = CartProductsApi(http_client=customer_client).create(
        {
            "product": str(ticket_product.id),
            "options": [],
            "ticket_info": VALID_TICKET_INFO,
        }
    )

    assert response.status_code == HTTP_201_CREATED
    existing_cart.refresh_from_db()
    assert existing_cart.prepared_cart_snapshot is None
    assert existing_cart.prepared_cart_hash is None


@pytest.mark.django_db
def test_cart_add_product_creates_new_cart_when_none_exists(customer_client, customer_user, ticket_product):
    response = CartProductsApi(http_client=customer_client).create(
        {
            "product": str(ticket_product.id),
            "options": [],
            "ticket_info": VALID_TICKET_INFO,
        }
    )
    assert response.status_code == HTTP_201_CREATED
    cart = Order.objects.get(user=customer_user)
    opr = cart.products.get(product=ticket_product)
    # 신규 Order / OPR 양쪽 모두 history 생성 (+) 확인 — REST 경로 통과 검증.
    assert list(cart.history.values_list("history_type", flat=True)) == ["+"]
    assert list(opr.history.values_list("history_type", flat=True)) == ["+"]


@pytest.mark.django_db
def test_cart_product_queryset_create_action_uses_unlocked_queryset(customer_user):
    view = CartProductViewSet()
    view.request = SimpleNamespace(user=customer_user)
    view.action = "create"

    assert list(view.get_queryset()) == []


@pytest.mark.django_db(transaction=True)
def test_cart_add_product_after_concurrent_free_checkout_creates_new_cart(customer_user, ticket_product):
    completed_cart = Order.objects.create(user=customer_user, name="cart")
    created_order_ids = []
    errors = []

    def add_product():
        db.close_old_connections()
        try:
            user = customer_user.__class__.objects.get(id=customer_user.id)
            serializer = ProductOrderableCheckSerializer(
                data={
                    "product": str(ticket_product.id),
                    "options": [],
                    "ticket_info": VALID_TICKET_INFO,
                },
                context={
                    "request": SimpleNamespace(user=user),
                    "mode": OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART,
                },
            )
            serializer.is_valid(raise_exception=True)
            created_order_ids.append(serializer.save().order_id)
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)
        finally:
            db.close_old_connections()

    with transaction.atomic():
        Order.objects.select_for_update().get(id=completed_cart.id)
        thread = threading.Thread(target=add_product)
        thread.start()
        time.sleep(0.2)
        PaymentHistory.objects.create(
            order=completed_cart,
            imp_id=None,
            status=PaymentHistoryStatus.completed,
            price=0,
        )

    thread.join(timeout=3)

    assert not thread.is_alive()
    assert errors == []
    assert created_order_ids != [completed_cart.id]
    assert not completed_cart.products.filter_active().exists()
    assert Order.objects.filter(user=customer_user).exclude(id=completed_cart.id).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_cart_add_without_existing_cart_reuses_one_cart(monkeypatch, customer_user, ticket_product):
    original_get_cart = ProductOrderableCheckSerializer._get_unpaid_cart_for_update
    no_cart_barrier = threading.Barrier(2)
    created_order_ids = []
    errors = []

    def delayed_get_cart(serializer):
        cart = original_get_cart(serializer)
        if cart is None:
            try:
                no_cart_barrier.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
        return cart

    monkeypatch.setattr(ProductOrderableCheckSerializer, "_get_unpaid_cart_for_update", delayed_get_cart)

    def add_product():
        db.close_old_connections()
        try:
            user = customer_user.__class__.objects.get(id=customer_user.id)
            serializer = ProductOrderableCheckSerializer(
                data={
                    "product": str(ticket_product.id),
                    "options": [],
                    "ticket_info": VALID_TICKET_INFO,
                },
                context={
                    "request": SimpleNamespace(user=user),
                    "mode": OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART,
                },
            )
            serializer.is_valid(raise_exception=True)
            created_order_ids.append(serializer.save().order_id)
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)
        finally:
            db.close_old_connections()

    threads = [threading.Thread(target=add_product) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(created_order_ids) == 2
    assert len(set(created_order_ids)) == 1
    cart = Order.objects.get(user=customer_user)
    assert cart.products.filter_active().count() == 2


@pytest.mark.django_db
def test_cart_add_revalidates_after_user_lock_before_saving(customer_user, ticket_product):
    ticket_product.max_quantity_per_user = 1
    ticket_product.save(update_fields=["max_quantity_per_user"])
    payload = {
        "product": str(ticket_product.id),
        "options": [],
        "ticket_info": VALID_TICKET_INFO,
    }
    context = {
        "request": SimpleNamespace(user=customer_user),
        "mode": OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART,
    }
    first_serializer = ProductOrderableCheckSerializer(data=payload, context=context)
    second_serializer = ProductOrderableCheckSerializer(data=payload, context=context)
    assert first_serializer.is_valid(raise_exception=True)
    assert second_serializer.is_valid(raise_exception=True)

    first_serializer.save()

    with pytest.raises(ValidationError) as exc_info:
        second_serializer.save()

    assert ProductNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(ticket_product.name) in str(
        exc_info.value.detail
    )
    assert OrderProductRelation.objects.filter(product=ticket_product, order__user=customer_user).count() == 1


@pytest.mark.django_db
def test_cart_add_product_rejects_invalid_product_id(customer_client):
    response = CartProductsApi(http_client=customer_client).create(
        {"product": "00000000-0000-0000-0000-000000000000", "options": []}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cart_remove_product_soft_deletes_pending_opr(customer_client, order_factory):
    pending_order = order_factory()
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=customer_client).delete(opr.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    opr.refresh_from_db()
    assert opr.deleted_at is not None
    # soft delete 는 `BaseAbstractModel.delete()` 가 deleted_at 만 update 하는 save() 이므로 history_type='~' 로 기록.
    types = list(opr.history.order_by("history_date").values_list("history_type", flat=True))
    assert types == ["+", "~"]


@pytest.mark.django_db
def test_cart_remove_product_invalidates_prepared_payment(customer_client, order_factory):
    pending_order = order_factory(status="prepared")
    opr = pending_order.products.first()

    response = CartProductsApi(http_client=customer_client).delete(opr.id)

    assert response.status_code == HTTP_204_NO_CONTENT
    pending_order.refresh_from_db()
    assert pending_order.prepared_cart_snapshot is None
    assert pending_order.prepared_cart_hash is None


@pytest.mark.django_db(transaction=True)
def test_cart_remove_product_after_concurrent_free_checkout_returns_404(customer_user, order_factory):
    pending_order = order_factory()
    opr = pending_order.products.first()
    responses = []

    def remove_product():
        db.close_old_connections()
        try:
            user = customer_user.__class__.objects.get(id=customer_user.id)
            client = APIClient()
            client.force_authenticate(user=user)
            responses.append(CartProductsApi(http_client=client).delete(opr.id))
        finally:
            db.close_old_connections()

    with transaction.atomic():
        Order.objects.select_for_update().get(id=pending_order.id)
        thread = threading.Thread(target=remove_product)
        thread.start()
        time.sleep(0.2)
        locked_opr = OrderProductRelation.objects.select_for_update().get(id=opr.id)
        locked_opr.status = OrderProductRelation.OrderProductStatus.paid
        locked_opr.save(update_fields=["status"])
        PaymentHistory.objects.create(
            order=pending_order,
            imp_id=None,
            status=PaymentHistoryStatus.completed,
            price=0,
        )

    thread.join(timeout=3)

    assert not thread.is_alive()
    assert len(responses) == 1
    assert responses[0].status_code == HTTP_404_NOT_FOUND
    opr.refresh_from_db()
    assert opr.deleted_at is None
    assert opr.status == OrderProductRelation.OrderProductStatus.paid


@pytest.mark.django_db
def test_cart_remove_product_rejects_other_users_opr(other_client, order_factory):
    pending_order = order_factory()
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=other_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cart_remove_product_rejects_already_paid_opr(customer_client, order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    response = CartProductsApi(http_client=customer_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cart_remove_product_returns_404_for_unauthenticated_request(anon_client, order_factory):
    pending_order = order_factory()
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=anon_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
