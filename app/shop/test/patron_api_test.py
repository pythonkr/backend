import pytest
from rest_framework.status import HTTP_200_OK
from shop.order.models import Order
from shop.test.helpers import PatronApi


@pytest.mark.django_db
def test_patron_list_includes_only_orders_with_donation_product(anon_client, customer_user, donation_completed_order):
    # 일반 (donation 무관한) order — 제외 검증.
    Order.objects.create(user=customer_user, name="reg")

    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == [{"name": "홍길동", "contribution_message": ""}]


@pytest.mark.django_db
def test_patron_list_excludes_refunded_orders(anon_client, donation_refunded_order):
    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_patron_list_excludes_orders_outside_year_filter(anon_client, donation_completed_order):
    # fixture order 의 created_at(2026) 과 다른 year=2020 → 빈 결과.
    response = PatronApi(http_client=anon_client).list({"year": 2020})
    assert response.status_code == HTTP_200_OK
    assert response.json() == []
