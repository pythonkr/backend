import pytest
from core.util.testutil import to_json
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from shop.order.models import Order, OrderProductRelation
from shop.order.serializers.dto import OrderDto
from shop.test.helpers import CartApi, CartProductsApi


@pytest.mark.django_db
def test_cart_returns_empty_dict_when_user_has_no_cart(customer_client):
    response = CartApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_returns_order_dto_when_cart_exists(pending_order, customer_client):
    response = CartApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json(OrderDto(instance=pending_order).data)


@pytest.mark.django_db
def test_cart_excludes_other_users_cart(pending_order, other_client):
    response = CartApi(http_client=other_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_returns_empty_when_request_unauthenticated(anon_client):
    response = CartApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {}


@pytest.mark.django_db
def test_cart_add_product_appends_to_existing_unpaid_cart(customer_client, customer_user, product):
    existing_cart = Order.objects.create(user=customer_user, name="cart")
    response = CartProductsApi(http_client=customer_client).create({"product": str(product.id), "options": []})
    assert response.status_code == HTTP_201_CREATED
    assert OrderProductRelation.objects.filter(order=existing_cart, product=product).exists()


@pytest.mark.django_db
def test_cart_add_product_creates_new_cart_when_none_exists(customer_client, customer_user, product):
    response = CartProductsApi(http_client=customer_client).create({"product": str(product.id), "options": []})
    assert response.status_code == HTTP_201_CREATED
    cart = Order.objects.get(user=customer_user)
    opr = cart.products.get(product=product)
    # 신규 Order / OPR 양쪽 모두 history 생성 (+) 확인 — REST 경로 통과 검증.
    assert list(cart.history.values_list("history_type", flat=True)) == ["+"]
    assert list(opr.history.values_list("history_type", flat=True)) == ["+"]


@pytest.mark.django_db
def test_cart_add_product_rejects_invalid_product_id(customer_client):
    response = CartProductsApi(http_client=customer_client).create(
        {"product": "00000000-0000-0000-0000-000000000000", "options": []}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cart_remove_product_soft_deletes_pending_opr(pending_order, customer_client):
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=customer_client).delete(opr.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    opr.refresh_from_db()
    assert opr.deleted_at is not None
    # soft delete 는 `BaseAbstractModel.delete()` 가 deleted_at 만 update 하는 save() 이므로 history_type='~' 로 기록.
    types = list(opr.history.order_by("history_date").values_list("history_type", flat=True))
    assert types == ["+", "~"]


@pytest.mark.django_db
def test_cart_remove_product_rejects_other_users_opr(pending_order, other_client):
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=other_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cart_remove_product_rejects_already_paid_opr(completed_order, customer_client):
    opr = completed_order.products.first()
    response = CartProductsApi(http_client=customer_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cart_remove_product_returns_404_for_unauthenticated_request(pending_order, anon_client):
    # 비인증 → ViewSet 의 get_queryset 이 `OrderProductRelation.objects.none()` 반환 → 404.
    opr = pending_order.products.first()
    response = CartProductsApi(http_client=anon_client).delete(opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
