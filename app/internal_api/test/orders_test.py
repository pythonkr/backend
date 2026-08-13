from datetime import timedelta

import pytest
from core.util.dateutil import now_aware
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from shop.order.models import OrderProductRelation, OrderProductRelationTag, TicketInfo
from shop.product.models import OptionGroup

ORDERS_URL = reverse("v1:registration_desk:orders-list")
SEARCH = {"keywords": "홍길동"}


def _detail_url(order_id) -> str:
    return reverse("v1:registration_desk:orders-detail", args=[order_id])


def _refund_url(order_id) -> str:
    return reverse("v1:registration_desk:orders-refund", args=[order_id])


@pytest.mark.django_db
def test_orders_rejects_anonymous(anon_client):
    assert anon_client.get(ORDERS_URL, SEARCH).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_orders_rejects_non_superuser(customer_client, order_factory):
    order_factory(status="completed")
    assert customer_client.get(ORDERS_URL, SEARCH).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_orders_list_returns_paginated_paid_orders(staff_client, order_factory):
    order = order_factory(status="completed")
    order_factory(status="cart")  # 결제 이력 없음 → 제외

    response = staff_client.get(ORDERS_URL, SEARCH)

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["count"] == 1
    assert [result["id"] for result in body["results"]] == [str(order.id)]
    assert body["results"][0]["customer_info"]["name"] == "홍길동"


@pytest.mark.django_db
def test_orders_list_exposes_ticket_info_and_product_category(staff_client, order_factory, ticket_product):
    order = order_factory(status="completed")
    TicketInfo.objects.create(
        order_product_relation=order.products.get(),
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
    )

    product = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]["products"][0]

    assert product["ticket_info"]["name"] == "김참가"
    assert product["is_ticket"] is True
    assert product["product"]["category"] == {"id": str(ticket_product.category_id), "name": "티켓"}


@pytest.mark.django_db
def test_orders_list_returns_null_ticket_info_when_absent(staff_client, order_factory):
    order_factory(status="completed")

    product = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]["products"][0]

    assert product["ticket_info"] is None


@pytest.mark.django_db
def test_orders_list_excludes_soft_deleted_products(staff_client, order_factory):
    order = order_factory(status="completed")
    order.products.get().delete()

    assert staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]["products"] == []


@pytest.mark.django_db
def test_orders_list_filters_by_keyword(staff_client, order_factory):
    order = order_factory(status="completed")

    assert staff_client.get(ORDERS_URL, {"keywords": "홍길동"}).json()["count"] == 1
    assert staff_client.get(ORDERS_URL, {"keywords": "없는사람"}).json()["count"] == 0
    assert staff_client.get(ORDERS_URL, {"order_id": str(order.id)}).json()["count"] == 1


@pytest.mark.django_db
def test_orders_list_filters_by_user_unique_id(staff_client, order_factory):
    orders = [order_factory(status="completed"), order_factory(status="completed")]

    response = staff_client.get(ORDERS_URL, {"user_unique_id": str(orders[0].user.unique_id)})

    assert {result["id"] for result in response.json()["results"]} == {str(order.id) for order in orders}


@pytest.mark.django_db
@pytest.mark.parametrize("keyword", ["김참가", "attendee@example.com", "010-9999-8888", "PSK"])
def test_orders_list_filters_by_ticket_info(staff_client, order_factory, keyword):
    order = order_factory(status="completed")
    TicketInfo.objects.create(
        order_product_relation=order.products.get(),
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
    )
    order_factory(status="completed")  # 참가자 정보 없는 다른 주문

    response = staff_client.get(ORDERS_URL, {"keywords": keyword})

    assert [result["id"] for result in response.json()["results"]] == [str(order.id)]


@pytest.mark.django_db
def test_orders_list_ignores_ticket_info_of_soft_deleted_product(staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()
    TicketInfo.objects.create(
        order_product_relation=opr, name="김참가", phone="010-9999-8888", email="attendee@example.com"
    )
    opr.delete()

    assert staff_client.get(ORDERS_URL, {"keywords": "김참가"}).json()["count"] == 0


@pytest.mark.django_db
def test_orders_patch_checks_in_paid_product(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()

    response = staff_client.patch(
        _detail_url(order.id),
        {"products": [{"id": str(opr.id), "status": OrderProductRelation.OrderProductStatus.used}]},
        format="json",
    )

    assert response.status_code == HTTP_200_OK
    opr.refresh_from_db()
    assert opr.status == OrderProductRelation.OrderProductStatus.used


@pytest.mark.django_db
def test_orders_patch_can_revert_check_in(ticket_config, staff_client, used_opr):
    response = staff_client.patch(
        _detail_url(used_opr.order_id),
        {"products": [{"id": str(used_opr.id), "status": OrderProductRelation.OrderProductStatus.paid}]},
        format="json",
    )

    assert response.status_code == HTTP_200_OK
    used_opr.refresh_from_db()
    assert used_opr.status == OrderProductRelation.OrderProductStatus.paid


@pytest.mark.django_db
def test_orders_patch_rejects_forbidden_status_transition(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()

    response = staff_client.patch(
        _detail_url(order.id),
        {"products": [{"id": str(opr.id), "status": OrderProductRelation.OrderProductStatus.refunded}]},
        format="json",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    opr.refresh_from_db()
    assert opr.status == OrderProductRelation.OrderProductStatus.paid


@pytest.mark.django_db
def test_orders_refund_cancels_payment_and_marks_products_refunded(
    ticket_config, staff_client, order_factory, mock_portone_req_cancel_payment
):
    order = order_factory(status="completed")

    response = staff_client.delete(_refund_url(order.id))

    assert response.status_code == HTTP_204_NO_CONTENT
    mock_portone_req_cancel_payment.assert_called_once()
    assert order.products.get().status == OrderProductRelation.OrderProductStatus.refunded


@pytest.mark.django_db
def test_orders_refund_rejects_non_superuser(customer_client, order_factory, mock_portone_req_cancel_payment):
    order = order_factory(status="completed")

    response = customer_client.delete(_refund_url(order.id))

    assert response.status_code == HTTP_403_FORBIDDEN
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_orders_does_not_expose_destroy(staff_client, order_factory):
    order = order_factory(status="completed")

    assert staff_client.delete(_detail_url(order.id)).status_code == 405


def _patch_ticket_info(client, order, opr, ticket_info):
    return client.patch(
        _detail_url(order.id),
        {"products": [{"id": str(opr.id), "ticket_info": ticket_info}]},
        format="json",
    )


VALID_TICKET_INFO = {
    "name": "김참가",
    "phone": "010-9999-8888",
    "email": "attendee@example.com",
    "organization": "PSK",
}


@pytest.mark.django_db
def test_orders_patch_creates_ticket_info(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()

    response = _patch_ticket_info(staff_client, order, opr, VALID_TICKET_INFO)

    assert response.status_code == HTTP_200_OK
    assert response.json()["products"][0]["ticket_info"] == VALID_TICKET_INFO
    assert TicketInfo.objects.get(order_product_relation=opr).name == "김참가"


@pytest.mark.django_db
def test_orders_patch_updates_existing_ticket_info(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()
    ticket_info = TicketInfo.objects.create(order_product_relation=opr, **VALID_TICKET_INFO)

    response = _patch_ticket_info(staff_client, order, opr, {**VALID_TICKET_INFO, "name": "이참가"})

    assert response.status_code == HTTP_200_OK
    ticket_info.refresh_from_db()
    assert ticket_info.name == "이참가"
    assert TicketInfo.objects.filter(order_product_relation=opr).count() == 1


@pytest.mark.django_db
def test_orders_patch_restores_soft_deleted_ticket_info(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()
    ticket_info = TicketInfo.objects.create(order_product_relation=opr, **VALID_TICKET_INFO)
    ticket_info.delete()

    response = _patch_ticket_info(staff_client, order, opr, VALID_TICKET_INFO)

    # OneToOne 이라 새 row 를 만들 수 없어, 삭제된 row 를 되살려 덮어쓴다.
    assert response.status_code == HTTP_200_OK
    ticket_info.refresh_from_db()
    assert ticket_info.deleted_at is None
    assert TicketInfo.objects.filter(order_product_relation=opr).count() == 1


@pytest.mark.django_db
def test_orders_patch_rejects_null_ticket_info(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()
    ticket_info = TicketInfo.objects.create(order_product_relation=opr, **VALID_TICKET_INFO)

    response = _patch_ticket_info(staff_client, order, opr, None)

    assert response.status_code == HTTP_400_BAD_REQUEST
    ticket_info.refresh_from_db()
    assert ticket_info.deleted_at is None


@pytest.mark.django_db
def test_orders_patch_keeps_ticket_info_when_key_is_omitted(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()
    TicketInfo.objects.create(order_product_relation=opr, **VALID_TICKET_INFO)

    response = staff_client.patch(
        _detail_url(order.id),
        {"products": [{"id": str(opr.id), "status": OrderProductRelation.OrderProductStatus.used}]},
        format="json",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["products"][0]["ticket_info"] == VALID_TICKET_INFO


@pytest.mark.django_db
def test_orders_patch_rejects_ticket_info_for_non_ticket_product(
    ticket_config, staff_client, order_factory, non_ticket_product
):
    order = order_factory(status="completed", is_ticket=False)
    opr = order.products.get()
    # 범위 검증(403)이 아니라 티켓 여부 검증(400)에 걸리도록 굿즈 카테고리도 설정에 포함시킨다.
    ticket_config.categories.add(non_ticket_product.category)

    response = _patch_ticket_info(staff_client, order, opr, VALID_TICKET_INFO)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not TicketInfo.objects.filter(order_product_relation=opr).exists()


@pytest.mark.django_db
def test_orders_patch_rejects_malformed_phone(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.get()

    response = _patch_ticket_info(staff_client, order, opr, {**VALID_TICKET_INFO, "phone": "전화번호아님"})

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not TicketInfo.objects.filter(order_product_relation=opr).exists()


@pytest.mark.django_db
def test_orders_list_requires_a_filter(staff_client, order_factory):
    order_factory(status="completed")

    response = staff_client.get(ORDERS_URL)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "keywords" in str(response.json())


@pytest.mark.django_db
def test_orders_list_rejects_pagination_only_request(staff_client, order_factory):
    order_factory(status="completed")

    assert staff_client.get(ORDERS_URL, {"page": 1, "page_size": 10}).status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_orders_list_rejects_blank_filter(staff_client, order_factory):
    order_factory(status="completed")

    assert staff_client.get(ORDERS_URL, {"keywords": "   "}).status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_orders_patch_rejects_ticket_info_for_refunded_product(ticket_config, staff_client, order_factory):
    order = order_factory(status="refunded")
    opr = order.products.get()

    response = _patch_ticket_info(staff_client, order, opr, VALID_TICKET_INFO)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not TicketInfo.objects.filter(order_product_relation=opr).exists()


@pytest.mark.django_db
def test_orders_patch_rejects_out_of_scope_product(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed", is_ticket=False)
    opr = order.products.get()

    response = staff_client.patch(
        _detail_url(order.id),
        {"products": [{"id": str(opr.id), "status": OrderProductRelation.OrderProductStatus.used}]},
        format="json",
    )

    assert response.status_code == HTTP_403_FORBIDDEN
    opr.refresh_from_db()
    assert opr.status == OrderProductRelation.OrderProductStatus.paid


@pytest.mark.django_db
def test_orders_patch_allows_reading_out_of_scope_order(ticket_config, staff_client, order_factory):
    order_factory(status="completed", is_ticket=False)

    assert staff_client.get(ORDERS_URL, SEARCH).json()["count"] == 1


@pytest.mark.django_db
def test_orders_refund_rejects_out_of_scope_order(
    ticket_config, staff_client, order_factory, mock_portone_req_cancel_payment
):
    order = order_factory(status="completed", is_ticket=False)

    response = staff_client.delete(_refund_url(order.id))

    assert response.status_code == HTTP_403_FORBIDDEN
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_orders_exposes_desk_refund_reasons(ticket_config, staff_client, order_factory):
    order_factory(status="completed")

    body = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]

    assert body["not_fully_refundable_reason"] is None
    assert body["products"][0]["not_refundable_reason"] is None
    assert body["created_at"] is not None


@pytest.mark.django_db
def test_orders_refund_reason_ignores_date_limit(ticket_config, staff_client, order_factory, ticket_product):
    # 데스크 환불은 환불 기한을 우회하므로, 기한 만료는 "환불 불가 사유" 로 응답하지 않는다.
    ticket_product.refundable_ends_at = now_aware() - timedelta(days=1)
    ticket_product.save()
    order_factory(status="completed")

    body = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]

    assert body["not_fully_refundable_reason"] is None
    assert body["products"][0]["not_refundable_reason"] is None


@pytest.mark.django_db
def test_orders_refund_reason_reports_used_product(ticket_config, staff_client, used_opr):
    body = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]

    assert body["products"][0]["not_refundable_reason"] is not None
    assert body["not_fully_refundable_reason"] is not None


@pytest.mark.django_db
def test_orders_patch_rejects_option_change_for_used_product(ticket_config, staff_client, modifiable_option_relation):
    opr = modifiable_option_relation.order_product_relation
    opr.status = OrderProductRelation.OrderProductStatus.used
    opr.save()

    response = staff_client.patch(
        _detail_url(opr.order_id),
        {
            "products": [
                {
                    "id": str(opr.id),
                    "options": [{"id": str(modifiable_option_relation.id), "custom_response": "변경"}],
                }
            ]
        },
        format="json",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_orders_patch_allows_null_custom_response(ticket_config, staff_client, modifiable_option_relation):
    opr = modifiable_option_relation.order_product_relation

    response = staff_client.patch(
        _detail_url(opr.order_id),
        {
            "products": [
                {
                    "id": str(opr.id),
                    "options": [{"id": str(modifiable_option_relation.id), "custom_response": None}],
                }
            ]
        },
        format="json",
    )

    assert response.status_code == HTTP_200_OK
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response is None


@pytest.mark.django_db
def test_orders_patch_rejects_null_custom_response_when_required(
    ticket_config, staff_client, modifiable_option_relation
):
    group = modifiable_option_relation.product_option_group
    group.placeholder_mode = OptionGroup.PlaceholderMode.REQUIRED
    group.save()

    response = staff_client.patch(
        _detail_url(modifiable_option_relation.order_product_relation.order_id),
        {
            "products": [
                {
                    "id": str(modifiable_option_relation.order_product_relation_id),
                    "options": [{"id": str(modifiable_option_relation.id), "custom_response": None}],
                }
            ]
        },
        format="json",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_orders_list_exposes_tags(ticket_config, staff_client, order_factory):
    order = order_factory(status="completed")
    tag = OrderProductRelationTag.objects.create(code="speaker", name="발표자", priority=1)
    tag.order_product_relations.add(order.products.get())

    body = staff_client.get(ORDERS_URL, SEARCH).json()["results"][0]

    assert body["products"][0]["tags"] == [{"id": str(tag.id), "code": "speaker", "name": "발표자", "priority": 1}]


@pytest.mark.django_db
def test_orders_patch_ignores_order_name(ticket_config, staff_client, order_factory):
    # 상품 외 필드가 열려 있으면 범위 검증 없이 주문을 바꿀 수 있다.
    order = order_factory(status="completed")

    response = staff_client.patch(_detail_url(order.id), {"name": "바뀐 이름"}, format="json")

    assert response.status_code == HTTP_200_OK
    order.refresh_from_db()
    assert order.name != "바뀐 이름"
