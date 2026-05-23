import pytest
from rest_framework.status import HTTP_200_OK
from shop.order.models import Order, OrderProductOptionRelation
from shop.product.models import OptionGroup
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


@pytest.mark.django_db
def test_patron_list_year_filter_matches_order_year(anon_client, donation_completed_order):
    # 현재 year(2026 — 테스트 환경) 와 일치 → 결과 포함.
    response = PatronApi(http_client=anon_client).list({"year": 2026})
    assert response.status_code == HTTP_200_OK
    assert response.json() == [{"name": "홍길동", "contribution_message": ""}]


@pytest.mark.django_db
def test_patron_list_returns_contribution_message_from_donation_option(anon_client, donation_completed_order, product):
    # "후원자" 가 포함된 option_group + is_custom_response=True → custom_response 가 contribution_message 로 노출.
    group = OptionGroup.objects.create(
        product=product,
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
def test_patron_list_response_excludes_user_pii(anon_client, donation_completed_order):
    # public API — 응답에 email / phone 등 PII 노출 금지.
    response = PatronApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    body = response.json()
    for item in body:
        assert set(item.keys()) == {"name", "contribution_message"}
