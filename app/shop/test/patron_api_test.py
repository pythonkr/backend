import pytest
from rest_framework.status import HTTP_200_OK
from shop.order.models import Order, OrderProductOptionRelation
from shop.product.models import OptionGroup
from shop.test.helpers import PatronApi


@pytest.mark.django_db
def test_patron_list_includes_only_orders_with_donation_product(anon_client, customer_user, order_factory):
    order_factory(status="completed", donation=5000)
    Order.objects.create(user=customer_user, name="reg")

    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == [{"name": "홍길동", "contribution_message": ""}]


@pytest.mark.django_db
def test_patron_list_excludes_refunded_orders(anon_client, order_factory):
    order_factory(status="refunded", donation=5000)
    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_patron_list_excludes_orders_outside_year_filter(anon_client, order_factory):
    order_factory(status="completed", donation=5000)
    response = PatronApi(http_client=anon_client).list({"year": 2020})
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_patron_list_year_filter_matches_order_year(anon_client, order_factory):
    order_factory(status="completed", donation=5000)
    response = PatronApi(http_client=anon_client).list({"year": 2026})
    assert response.status_code == HTTP_200_OK
    assert response.json() == [{"name": "홍길동", "contribution_message": ""}]


@pytest.mark.django_db
def test_patron_list_returns_contribution_message_from_donation_option(anon_client, ticket_product, order_factory):
    donation_completed_order = order_factory(status="completed", donation=5000)
    group = OptionGroup.objects.create(
        product=ticket_product,
        name="후원자 한마디",
        is_custom_response=True,
        custom_response_pattern=r"^.*$",
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=donation_completed_order.products.first(),
        product_option_group=group,
        custom_response="응원합니다!",
    )

    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == [{"name": "홍길동", "contribution_message": "응원합니다!"}]


@pytest.mark.django_db
def test_patron_list_response_excludes_user_pii(anon_client, order_factory):
    order_factory(status="completed", donation=5000)
    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    body = response.json()
    for item in body:
        assert set(item.keys()) == {"name", "contribution_message"}
