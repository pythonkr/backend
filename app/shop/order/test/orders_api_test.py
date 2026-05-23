from unittest.mock import patch

import pytest
from core.const.shop_error_messages import CartNotOrderableErrorMessages
from core.external_apis.portone.client import PortOneException
from core.util.testutil import to_json
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart
from shop.order.serializers.dto import OrderDto, SingleProductCartDto
from shop.payment_history.models import PaymentHistoryStatus
from shop.test.helpers import OrdersApi


@pytest.mark.django_db
def test_order_list_returns_empty_for_unauthenticated_request(anon_client):
    response = OrdersApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_order_list_returns_only_orders_with_payment_history(customer_client, completed_order, empty_cart):
    response = OrdersApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json([OrderDto(instance=completed_order).data])


@pytest.mark.django_db
def test_order_list_excludes_other_users_orders(other_client, completed_order):
    response = OrdersApi(http_client=other_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_order_retrieve_returns_full_order_dto(customer_client, completed_order):
    response = OrdersApi(http_client=customer_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json(OrderDto(instance=completed_order).data)


@pytest.mark.django_db
def test_order_retrieve_returns_404_for_other_users_order(other_client, completed_order):
    response = OrdersApi(http_client=other_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_create_single_product_order_creates_cart_and_calls_portone(
    customer_client, customer_user, product, mock_portone_register
):
    response = OrdersApi(http_client=customer_client).create_single(
        {
            "product": str(product.id),
            "options": [],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "customer@example.com",
                "organization": "",
            },
        }
    )
    assert response.status_code == HTTP_201_CREATED
    cart = SingleProductCart.objects.get(user=customer_user)
    assert response.json() == SingleProductCartDto(instance=cart).data
    mock_portone_register.assert_called_once_with(merchant_id=str(cart.id), price=product.price)
    # SingleProductCart + OPR 양쪽 history 생성 확인.
    assert list(cart.history.values_list("history_type", flat=True)) == ["+"]
    assert list(cart.order_product_relation.history.values_list("history_type", flat=True)) == ["+"]


@pytest.mark.django_db
def test_create_single_product_order_rejects_invalid_product(customer_client, mock_portone_register):
    response = OrdersApi(http_client=customer_client).create_single(
        {
            "product": "00000000-0000-0000-0000-000000000000",
            "options": [],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "customer@example.com",
                "organization": "",
            },
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_register.assert_not_called()


@pytest.mark.django_db
def test_create_order_rejects_when_cart_is_empty(customer_client, empty_cart, mock_portone_register):
    response = OrdersApi(http_client=customer_client).create(
        {"name": "홍길동", "phone": "010-1234-5678", "email": "customer@example.com", "organization": ""}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert CartNotOrderableErrorMessages.EMPTY in str(response.json())
    mock_portone_register.assert_not_called()


@pytest.mark.django_db
def test_create_order_persists_customer_info_and_schedules_portone_call(
    customer_client, customer_user, product, mock_portone_register
):
    cart = Order.objects.create(user=customer_user, name="cart")
    OrderProductRelation.objects.create(order=cart, product=product, price=product.price)

    # on_commit 은 test transaction rollback 으로 실제 발화 안 되지만 등록은 검증 가능.
    with patch("shop.order.views.orders.transaction.on_commit") as mocked_on_commit:
        response = OrdersApi(http_client=customer_client).create(
            {"name": "홍길동", "phone": "010-1234-5678", "email": "customer@example.com", "organization": ""}
        )

    assert response.status_code == HTTP_201_CREATED
    cart.refresh_from_db()
    assert response.json() == OrderDto(instance=cart).data
    assert CustomerInfo.objects.filter(order=cart, name="홍길동").exists()
    mocked_on_commit.assert_called_once()


@pytest.mark.django_db
def test_destroy_order_refunds_when_owned_by_request_user(
    customer_client, completed_order, mock_portone_req_cancel_payment
):
    opr = completed_order.products.first()
    response = OrdersApi(http_client=customer_client).delete(completed_order.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    completed_order.refresh_from_db()
    statuses = list(completed_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.refunded]
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.refunded).exists()
    # `bulk_update_with_history` 경로가 OPR 상태 변경 history 를 잘 남기는지 확인 — 누락 시 회귀.
    assert opr.history.filter(history_type="~", status=OrderProductRelation.OrderProductStatus.refunded).exists()


@pytest.mark.django_db
def test_destroy_order_rejects_other_users_order(other_client, completed_order, mock_portone_req_cancel_payment):
    response = OrdersApi(http_client=other_client).delete(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_retrieve_receipt_returns_kcp_redirect_html_for_owner(
    customer_client, completed_order, mock_portone_kcp_receipt
):
    mock_portone_kcp_receipt.return_value.to_search_data.return_value = {"x": "y"}
    mock_portone_kcp_receipt.return_value.to_kcp_signed_search_data.return_value = "signed"
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_200_OK
    mock_portone_kcp_receipt.assert_called_once_with(imp_uid=completed_order.latest_imp_id)


@pytest.mark.django_db
def test_retrieve_receipt_returns_404_when_order_has_no_imp_id(customer_client, pending_order):
    response = OrdersApi(http_client=customer_client).retrieve_receipt(pending_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieve_receipt_returns_404_when_payment_history_has_no_imp_id(customer_client, completed_order):
    # CSV import 경로처럼 imp_id=None — queryset 필터는 통과하나 action body 에서 404 HTML.
    completed_order.payment_histories.update(imp_id=None)
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieve_receipt_allows_staff_to_access_any_order(staff_client, completed_order, mock_portone_kcp_receipt):
    mock_portone_kcp_receipt.return_value.to_search_data.return_value = {"x": "y"}
    mock_portone_kcp_receipt.return_value.to_kcp_signed_search_data.return_value = "signed"
    response = OrdersApi(http_client=staff_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_retrieve_receipt_returns_500_when_portone_unavailable(
    customer_client, completed_order, mock_portone_kcp_receipt
):
    mock_portone_kcp_receipt.side_effect = PortOneException("down")
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
