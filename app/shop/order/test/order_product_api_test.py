import pytest
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_404_NOT_FOUND
from shop.order.models import OrderProductRelation
from shop.payment_history.models import PaymentHistoryStatus
from shop.test.helpers import OrderProductsApi


@pytest.mark.django_db
def test_modify_options_updates_custom_response(modifiable_option_relation, completed_order, customer_client):
    opr = completed_order.products.first()
    response = OrderProductsApi(http_client=customer_client).modify_options(
        completed_order.id,
        opr.id,
        [{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "updated"}],
    )
    assert response.status_code == HTTP_200_OK
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response == "updated"
    # PATCH 가 OPOR custom_response 변경 history 를 남기는지 확인 — 응답 수정 감사 추적.
    assert modifiable_option_relation.history.filter(history_type="~", custom_response="updated").exists()


@pytest.mark.django_db
def test_modify_options_rejects_other_users_opr(modifiable_option_relation, completed_order, other_client):
    opr = completed_order.products.first()
    response = OrderProductsApi(http_client=other_client).modify_options(
        completed_order.id,
        opr.id,
        [{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "updated"}],
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_order_product_refunds_partially(
    customer_client, completed_order, product, mock_portone_req_cancel_payment
):
    # 두 번째 paid OPR 추가 → 첫 OPR 환불 시 partial_refunded 기록.
    target_opr = completed_order.products.first()
    OrderProductRelation.objects.create(
        order=completed_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    response = OrderProductsApi(http_client=customer_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.partial_refunded).exists()


@pytest.mark.django_db
def test_destroy_order_product_rejects_other_users_opr(other_client, completed_order, mock_portone_req_cancel_payment):
    target_opr = completed_order.products.first()
    response = OrderProductsApi(http_client=other_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_destroy_order_product_rejects_when_status_not_paid(
    customer_client, completed_order, mock_portone_req_cancel_payment
):
    target_opr = completed_order.products.first()
    target_opr.status = OrderProductRelation.OrderProductStatus.used
    target_opr.save()
    response = OrderProductsApi(http_client=customer_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_destroy_order_product_returns_404_for_unauthenticated_request(anon_client, completed_order):
    # 비인증 → ViewSet 의 get_queryset 이 `OrderProductRelation.objects.none()` 반환 → 404.
    response = OrderProductsApi(http_client=anon_client).delete_partial(
        completed_order.id, completed_order.products.first().id
    )
    assert response.status_code == HTTP_404_NOT_FOUND
