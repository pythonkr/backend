import pytest
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_404_NOT_FOUND
from shop.order.models import OrderProductRelation
from shop.payment_history.models import PaymentHistoryStatus
from shop.test.helpers import OrderProductsApi


@pytest.mark.django_db
def test_modify_options_updates_custom_response(modifiable_option_relation, customer_client):
    # `modifiable_option_relation` fixture 가 이미 completed_order 를 생성 + OPOR 를 거기 OPR 에 attach.
    opr = modifiable_option_relation.order_product_relation
    response = OrderProductsApi(http_client=customer_client).modify_options(
        opr.order_id,
        opr.id,
        [{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "updated"}],
    )
    assert response.status_code == HTTP_200_OK
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response == "updated"
    # PATCH 가 OPOR custom_response 변경 history 를 남기는지 확인 — 응답 수정 감사 추적.
    assert modifiable_option_relation.history.filter(history_type="~", custom_response="updated").exists()


@pytest.mark.django_db
def test_modify_options_rejects_other_users_opr(modifiable_option_relation, other_client):
    opr = modifiable_option_relation.order_product_relation
    response = OrderProductsApi(http_client=other_client).modify_options(
        opr.order_id,
        opr.id,
        [{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "updated"}],
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_order_product_refunds_partially(
    customer_client, ticket_product, mock_portone_req_cancel_payment, order_factory
):
    completed_order = order_factory(status="completed")
    target_opr = completed_order.products.first()
    OrderProductRelation.objects.create(
        order=completed_order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    response = OrderProductsApi(http_client=customer_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.partial_refunded).exists()


@pytest.mark.django_db
def test_destroy_order_product_rejects_other_users_opr(other_client, mock_portone_req_cancel_payment, order_factory):
    completed_order = order_factory(status="completed")
    target_opr = completed_order.products.first()
    response = OrderProductsApi(http_client=other_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_destroy_order_product_rejects_when_status_not_paid(
    customer_client, mock_portone_req_cancel_payment, order_factory
):
    completed_order = order_factory(status="completed")
    target_opr = completed_order.products.first()
    target_opr.status = OrderProductRelation.OrderProductStatus.used
    target_opr.save()
    response = OrderProductsApi(http_client=customer_client).delete_partial(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_destroy_order_product_returns_404_for_unauthenticated_request(anon_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrderProductsApi(http_client=anon_client).delete_partial(
        completed_order.id, completed_order.products.first().id
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_modify_options_rejects_opr_from_another_order_of_same_user(
    modifiable_option_relation, customer_client, order_factory
):
    # 같은 사용자의 다른 주문 URL 로 OPR rel_id 를 끼워넣어 수정 시도 — URL 의 order_id 가 강제돼야 함.
    opr = modifiable_option_relation.order_product_relation
    foreign_order = order_factory(status="completed")
    response = OrderProductsApi(http_client=customer_client).modify_options(
        foreign_order.id,
        opr.id,
        [{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "updated"}],
    )
    assert response.status_code == HTTP_404_NOT_FOUND
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response != "updated"


@pytest.mark.django_db
def test_destroy_order_product_rejects_opr_from_another_order_of_same_user(
    customer_client, mock_portone_req_cancel_payment, order_factory
):
    # 같은 사용자의 다른 주문 URL 로 환불을 시도해도 거절 — cross-order rel_id 사용 차단.
    target_order = order_factory(status="completed")
    foreign_order = order_factory(status="completed")
    target_opr = target_order.products.first()
    response = OrderProductsApi(http_client=customer_client).delete_partial(foreign_order.id, target_opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.paid
    mock_portone_req_cancel_payment.assert_not_called()
