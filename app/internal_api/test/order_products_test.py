import uuid

import pytest
from django.urls import reverse
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)
from shop.order.models import OrderProductRelation, TicketInfo

LIST_URL = reverse("v1:registration_desk:order-products-list")


def _refund_url(opr_id) -> str:
    return reverse("v1:registration_desk:order-products-refund", args=[opr_id])


def _results(response) -> list[dict]:
    return response.json()["results"]


@pytest.mark.django_db
def test_order_product_list_rejects_anonymous(anon_client, order_factory):
    opr = order_factory(status="completed").products.get()
    assert anon_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)}).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_order_product_list_rejects_non_superuser(customer_client, order_factory):
    opr = order_factory(status="completed").products.get()
    assert customer_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)}).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_order_product_list_requires_a_filter(staff_client):
    response = staff_client.get(LIST_URL)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "order_product_relation_id" in str(response.json())


@pytest.mark.django_db
def test_order_product_list_rejects_both_filters(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()

    response = staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id), "scancode": opr.scancode_token})

    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_order_product_list_returns_detail_by_id(staff_client, order_factory, ticket_product):
    order = order_factory(status="completed")
    opr = order.products.get()

    response = staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)})

    assert response.status_code == HTTP_200_OK
    assert response.json()["count"] == 1
    [body] = _results(response)
    assert body["id"] == str(opr.id)
    assert body["short_id"] == opr.short_id
    assert body["scancode_token"] == opr.scancode_token
    assert body["is_ticket"] is True
    assert body["status"] == OrderProductRelation.OrderProductStatus.paid
    assert body["product"]["name"] == ticket_product.name
    assert body["product"]["category"] == {"id": str(ticket_product.category_id), "name": "티켓"}
    assert body["order"]["id"] == str(order.id)
    assert body["ticket_info"] is None


@pytest.mark.django_db
def test_order_product_list_marks_non_ticket_product(staff_client, order_factory):
    opr = order_factory(status="completed", is_ticket=False).products.get()

    [body] = _results(staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)}))

    assert body["is_ticket"] is False


@pytest.mark.django_db
def test_order_product_list_returns_ticket_info(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()
    TicketInfo.objects.create(
        order_product_relation=opr,
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
    )

    [body] = _results(staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)}))

    assert body["ticket_info"] == {
        "name": "김참가",
        "email": "attendee@example.com",
        "phone": "010-9999-8888",
        "organization": "PSK",
    }


@pytest.mark.django_db
def test_order_product_list_returns_null_ticket_info_when_soft_deleted(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()
    TicketInfo.objects.create(
        order_product_relation=opr, name="김참가", phone="010-9999-8888", email="attendee@example.com"
    ).delete()

    [body] = _results(staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)}))

    assert body["ticket_info"] is None


@pytest.mark.django_db
def test_order_product_list_returns_empty_for_unknown_id(staff_client):
    response = staff_client.get(LIST_URL, {"order_product_relation_id": str(uuid.uuid4())})

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"count": 0, "next": None, "previous": None, "results": []}


@pytest.mark.django_db
def test_order_product_list_returns_empty_for_soft_deleted_relation(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()
    opr.delete()

    assert _results(staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)})) == []


@pytest.mark.django_db
def test_order_product_list_excludes_cart_without_payment(staff_client, order_factory):
    opr = order_factory(status="cart").products.get()

    assert _results(staff_client.get(LIST_URL, {"order_product_relation_id": str(opr.id)})) == []


@pytest.mark.django_db
def test_order_product_list_finds_by_scancode(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()

    [body] = _results(staff_client.get(LIST_URL, {"scancode": opr.scancode_token}))

    assert body["id"] == str(opr.id)


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["그냥문자열", "opr:short", "order:AbCdEf:salt"])
def test_order_product_list_rejects_malformed_scancode(staff_client, token):
    response = staff_client.get(LIST_URL, {"scancode": token})

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "스캔코드" in str(response.json())


@pytest.mark.django_db
def test_order_product_list_returns_empty_for_tampered_salt(staff_client, order_factory):
    opr = order_factory(status="completed").products.get()
    prefix, short_id, _salt = opr.scancode_token.split(":")

    response = staff_client.get(LIST_URL, {"scancode": f"{prefix}:{short_id}:tampered"})

    assert response.status_code == HTTP_200_OK
    assert _results(response) == []


@pytest.mark.django_db
def test_order_product_refund_rejects_non_superuser(customer_client, order_factory, mock_portone_req_cancel_payment):
    opr = order_factory(status="completed").products.get()

    response = customer_client.delete(_refund_url(opr.id))

    assert response.status_code == HTTP_403_FORBIDDEN
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_order_product_refund_marks_only_that_product_refunded(
    ticket_config, staff_client, order_factory, ticket_product, mock_portone_req_cancel_payment
):
    order = order_factory(status="completed")
    target = order.products.get()
    other = OrderProductRelation.objects.create(
        order=order, product=ticket_product, price=ticket_product.price, status=target.status
    )

    response = staff_client.delete(_refund_url(target.id))

    assert response.status_code == HTTP_204_NO_CONTENT
    mock_portone_req_cancel_payment.assert_called_once()
    target.refresh_from_db()
    other.refresh_from_db()
    assert target.status == OrderProductRelation.OrderProductStatus.refunded
    assert other.status == OrderProductRelation.OrderProductStatus.paid


@pytest.mark.django_db
def test_order_product_refund_rejects_used_product(
    ticket_config, staff_client, used_opr, mock_portone_req_cancel_payment
):
    response = staff_client.delete(_refund_url(used_opr.id))

    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_req_cancel_payment.assert_not_called()
