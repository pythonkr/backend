from datetime import datetime, timezone

import pytest
from admin_api.serializers.shop.orders import OrderAdminSerializer
from admin_api.views.shop.orders import OrderAdminViewSet
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.test.helpers import OrdersAdminApi, valid_refund_totp


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_admin_list_rejects_non_superuser_client(request, client_fixture):
    response = OrdersAdminApi(http_client=request.getfixturevalue(client_fixture)).list()
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_returns_only_orders_with_payment_history_and_products(api_client, completed_order, empty_cart):
    response = OrdersAdminApi(http_client=api_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_status_csv(api_client, completed_order, refunded_order):
    response = OrdersAdminApi(http_client=api_client).list({"status": "refunded"})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=refunded_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_product_id_distinct(api_client, completed_order, product):
    # distinct=True 라 OPR 여러 개 매칭돼도 같은 order 한 번만 반환.
    response = OrdersAdminApi(http_client=api_client).list({"product_id": str(product.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_retrieve_returns_nested_payload(api_client, completed_order):
    response = OrdersAdminApi(http_client=api_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data


@pytest.mark.django_db
def test_admin_refund_action_refunds_order_with_valid_totp(
    api_client, completed_order, mock_portone_req_cancel_payment
):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp=valid_refund_totp())
    assert response.status_code == HTTP_204_NO_CONTENT
    completed_order.refresh_from_db()
    statuses = list(completed_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.refunded]
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_action_rejects_invalid_totp(api_client, completed_order, mock_portone_req_cancel_payment):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp="000000")
    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_action_rejects_missing_totp(api_client, completed_order, mock_portone_req_cancel_payment):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id)
    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_product_action_does_partial_refund(
    api_client, completed_order, product, mock_portone_req_cancel_payment
):
    target_opr = completed_order.products.first()
    OrderProductRelation.objects.create(
        order=completed_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed_order.id, target_opr.id, totp=valid_refund_totp()
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    # OrderProductRefundSerializer 가 직접 OPR.save() 호출 — history_type='~' 기록 검증.
    assert target_opr.history.filter(history_type="~", status=OrderProductRelation.OrderProductStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_product_action_returns_404_for_unknown_rel(api_client, completed_order):
    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed_order.id, "00000000-0000-0000-0000-000000000000", totp=valid_refund_totp()
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_refund_allows_expired_window(api_client, completed_order, mock_portone_req_cancel_payment):
    # admin endpoint 는 check_refundable_date=False 로 expired 상품도 환불 가능.
    product = completed_order.products.first().product
    product.refundable_ends_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    product.save()

    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp=valid_refund_totp())
    assert response.status_code == HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_admin_import_template_returns_csv(api_client, product):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id=str(product.id))
    assert response.status_code == HTTP_200_OK
    assert "text/csv" in response.headers["Content-Type"]


@pytest.mark.django_db
def test_admin_import_template_rejects_missing_product_id(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template()
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_import_template_returns_404_for_unknown_product(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id="00000000-0000-0000-0000-000000000000")
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_list_filters_by_user_id(api_client, completed_order, customer_user, other_user, product):
    other_order = Order.objects.create(user=other_user, name="other")
    OrderProductRelation.objects.create(
        order=other_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    PaymentHistory.objects.create(
        order=other_order, imp_id="imp_o", status=PaymentHistoryStatus.completed, price=product.price
    )

    response = OrdersAdminApi(http_client=api_client).list({"user_id": str(customer_user.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }
