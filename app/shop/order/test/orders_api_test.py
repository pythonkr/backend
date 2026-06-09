from datetime import timedelta
from unittest.mock import patch

import pytest
from core.const.shop_error_messages import CartNotOrderableErrorMessages
from core.external_apis.portone.client import PortOneException
from core.util.testutil import to_json
from django.utils import timezone
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from shop.conftest import VALID_TICKET_INFO
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart, TicketInfo
from shop.order.serializers.dto import OrderDto, SingleProductCartDto
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.test.helpers import OrdersApi


@pytest.mark.django_db
def test_order_list_returns_empty_for_unauthenticated_request(anon_client):
    response = OrdersApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_order_list_returns_only_orders_with_payment_history(customer_client, order_factory):
    completed_order = order_factory(status="completed")
    order_factory(status="empty")
    response = OrdersApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json([OrderDto(instance=completed_order).data])


@pytest.mark.django_db
def test_order_list_excludes_other_users_orders(other_client, order_factory):
    order_factory(status="completed")
    response = OrdersApi(http_client=other_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_order_list_orders_by_first_paid_at_desc(customer_client, order_factory):
    # 먼저 생성된 주문(= Order.created_at 이 더 과거)이 더 최근에 결제되도록 구성.
    # 이렇게 해야 created_at 기본 정렬과 first_paid_at 정렬의 결과가 달라져 검증이 유효하다.
    older_order = order_factory(status="completed")
    newer_order = order_factory(status="completed")
    now = timezone.now()
    PaymentHistory.objects.filter(order=older_order).update(created_at=now)
    PaymentHistory.objects.filter(order=newer_order).update(created_at=now - timedelta(days=1))

    response = OrdersApi(http_client=customer_client).list()

    assert response.status_code == HTTP_200_OK
    assert [order["id"] for order in response.json()] == [str(older_order.id), str(newer_order.id)]


@pytest.mark.django_db
def test_order_retrieve_returns_full_order_dto(customer_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersApi(http_client=customer_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == to_json(OrderDto(instance=completed_order).data)


@pytest.mark.django_db
def test_order_retrieve_returns_404_for_other_users_order(other_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersApi(http_client=other_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_create_single_product_order_creates_cart_and_calls_portone(
    customer_client, customer_user, ticket_product, mock_portone_register
):
    response = OrdersApi(http_client=customer_client).create_single(
        {
            "product": str(ticket_product.id),
            "options": [],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "customer@example.com",
                "organization": "",
            },
            "ticket_info": VALID_TICKET_INFO,
        }
    )
    assert response.status_code == HTTP_201_CREATED
    cart = SingleProductCart.objects.get(user=customer_user)
    assert response.json() == SingleProductCartDto(instance=cart).data
    assert cart.prepared_cart_snapshot is not None
    assert cart.prepared_cart_hash is not None
    assert cart.prepared_price == ticket_product.price
    mock_portone_register.assert_called_once_with(merchant_id=cart.merchant_uid, price=ticket_product.price)
    # SingleProductCart + OPR 양쪽 history 생성 확인.
    assert list(cart.history.order_by("history_date").values_list("history_type", flat=True)) == ["+", "~"]
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
def test_create_order_rejects_when_cart_is_empty(customer_client, mock_portone_register, order_factory):
    order_factory(status="empty")
    response = OrdersApi(http_client=customer_client).create(
        {"name": "홍길동", "phone": "010-1234-5678", "email": "customer@example.com", "organization": ""}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert CartNotOrderableErrorMessages.EMPTY in str(response.json())
    mock_portone_register.assert_not_called()


@pytest.mark.django_db
def test_create_order_persists_customer_info_and_schedules_portone_call(
    customer_client, customer_user, ticket_product, mock_portone_register
):
    cart = Order.objects.create(user=customer_user, name="cart")
    opr = OrderProductRelation.objects.create(order=cart, product=ticket_product, price=ticket_product.price)
    TicketInfo.objects.create(
        order_product_relation=opr, name="김참가", phone="010-9999-8888", email="attendee@example.com"
    )

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
    customer_client, mock_portone_req_cancel_payment, order_factory
):
    completed_order = order_factory(status="completed")
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
def test_destroy_order_rejects_other_users_order(other_client, mock_portone_req_cancel_payment, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersApi(http_client=other_client).delete(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_retrieve_receipt_returns_kcp_redirect_html_for_owner(customer_client, mock_portone_kcp_receipt, order_factory):
    completed_order = order_factory(status="completed")
    mock_portone_kcp_receipt.return_value.to_search_data.return_value = {"x": "y"}
    mock_portone_kcp_receipt.return_value.to_kcp_signed_search_data.return_value = "signed"
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_200_OK
    mock_portone_kcp_receipt.assert_called_once_with(imp_uid=completed_order.latest_imp_id)


@pytest.mark.django_db
def test_retrieve_receipt_returns_404_when_order_has_no_imp_id(customer_client, order_factory):
    pending_order = order_factory()
    response = OrdersApi(http_client=customer_client).retrieve_receipt(pending_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieve_receipt_returns_404_when_payment_history_has_no_imp_id(customer_client, order_factory):
    completed_order = order_factory(status="completed")
    completed_order.payment_histories.update(imp_id=None)
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieve_receipt_allows_staff_to_access_any_order(staff_client, mock_portone_kcp_receipt, order_factory):
    completed_order = order_factory(status="completed")
    mock_portone_kcp_receipt.return_value.to_search_data.return_value = {"x": "y"}
    mock_portone_kcp_receipt.return_value.to_kcp_signed_search_data.return_value = "signed"
    response = OrdersApi(http_client=staff_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_retrieve_receipt_returns_500_when_portone_unavailable(
    customer_client, mock_portone_kcp_receipt, order_factory
):
    completed_order = order_factory(status="completed")
    mock_portone_kcp_receipt.side_effect = PortOneException("down")
    response = OrdersApi(http_client=customer_client).retrieve_receipt(completed_order.id)
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
