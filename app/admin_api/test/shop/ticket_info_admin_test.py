import pytest
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from shop.conftest import VALID_TICKET_INFO
from shop.order.models import TicketInfo
from shop.product.models import Category
from shop.test.helpers import CategoryGroupsAdminApi, OrdersAdminApi


def _patch_is_ticket(api_client, category: Category, *, is_ticket: bool):
    return CategoryGroupsAdminApi(http_client=api_client).update(
        category.group_id,
        {
            "categories": [
                {
                    "id": str(category.id),
                    "name": category.name,
                    "priority": category.priority,
                    "is_ticket": is_ticket,
                }
            ]
        },
    )


# ==================== is_ticket freeze — 구매 건이 있는 카테고리 ====================


@pytest.mark.django_db
def test_admin_cannot_unset_is_ticket_when_purchased_ticket_has_ticket_info(api_client, ticket_opr):
    TicketInfo.objects.create(order_product_relation=ticket_opr, **VALID_TICKET_INFO)
    response = _patch_is_ticket(api_client, ticket_opr.product.category, is_ticket=False)
    assert response.status_code == HTTP_400_BAD_REQUEST
    ticket_opr.product.category.refresh_from_db()
    assert ticket_opr.product.category.is_ticket is True


@pytest.mark.django_db
def test_admin_can_unset_is_ticket_when_no_ticket_info_collected(api_client, ticket_opr):
    # 구매 티켓이지만 참가자 정보 미수집 → 해제 허용.
    response = _patch_is_ticket(api_client, ticket_opr.product.category, is_ticket=False)
    assert response.status_code == HTTP_200_OK
    ticket_opr.product.category.refresh_from_db()
    assert ticket_opr.product.category.is_ticket is False


@pytest.mark.django_db
def test_admin_cannot_set_is_ticket_when_purchased_non_ticket_lacks_ticket_info(api_client, non_ticket_opr):
    response = _patch_is_ticket(api_client, non_ticket_opr.product.category, is_ticket=True)
    assert response.status_code == HTTP_400_BAD_REQUEST
    non_ticket_opr.product.category.refresh_from_db()
    assert non_ticket_opr.product.category.is_ticket is False


@pytest.mark.django_db
def test_admin_can_set_is_ticket_when_all_purchased_have_ticket_info(api_client, non_ticket_opr):
    TicketInfo.objects.create(order_product_relation=non_ticket_opr, **VALID_TICKET_INFO)
    response = _patch_is_ticket(api_client, non_ticket_opr.product.category, is_ticket=True)
    assert response.status_code == HTTP_200_OK
    non_ticket_opr.product.category.refresh_from_db()
    assert non_ticket_opr.product.category.is_ticket is True


# ==================== 어드민 주문 조회 — ticket_info 노출 ====================


@pytest.mark.django_db
def test_admin_order_exposes_ticket_info(api_client, ticket_opr):
    TicketInfo.objects.create(order_product_relation=ticket_opr, **VALID_TICKET_INFO, contribution_message="응원")
    response = OrdersAdminApi(http_client=api_client).retrieve(ticket_opr.order_id)
    assert response.status_code == HTTP_200_OK
    product_dto = next(p for p in response.json()["products"] if p["id"] == str(ticket_opr.id))
    assert product_dto["ticket_info"] == {**VALID_TICKET_INFO, "contribution_message": "응원"}
