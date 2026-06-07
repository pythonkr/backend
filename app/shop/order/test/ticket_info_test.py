import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from shop.conftest import VALID_TICKET_INFO
from shop.order.models import OrderProductRelation, TicketInfo
from shop.test.helpers import CartProductsApi, OrderProductsApi, OrdersApi


def _attr(response) -> str:
    return response.json()["errors"][0]["attr"]


# ==================== 인라인 입력 — 장바구니 담기(ADD_SINGLE_PRODUCT_TO_CART) ====================


@pytest.mark.django_db
def test_cart_add_ticket_requires_ticket_info(customer_client, ticket_product):
    response = CartProductsApi(http_client=customer_client).create({"product": str(ticket_product.id), "options": []})
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert _attr(response) == "ticket_info"


@pytest.mark.django_db
def test_cart_add_ticket_persists_ticket_info(customer_client, customer_user, ticket_product):
    response = CartProductsApi(http_client=customer_client).create(
        {"product": str(ticket_product.id), "options": [], "ticket_info": VALID_TICKET_INFO}
    )
    assert response.status_code == HTTP_201_CREATED
    opr = OrderProductRelation.objects.get(product=ticket_product, order__user=customer_user)
    assert TicketInfo.objects.filter(order_product_relation=opr, name=VALID_TICKET_INFO["name"]).exists()


@pytest.mark.django_db
def test_cart_add_non_ticket_forbids_ticket_info(customer_client, non_ticket_product):
    response = CartProductsApi(http_client=customer_client).create(
        {"product": str(non_ticket_product.id), "options": [], "ticket_info": VALID_TICKET_INFO}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert _attr(response) == "ticket_info"


@pytest.mark.django_db
def test_cart_add_contribution_message_rejected_for_non_donation_ticket(customer_client, ticket_product):
    response = CartProductsApi(http_client=customer_client).create(
        {
            "product": str(ticket_product.id),
            "options": [],
            "ticket_info": {**VALID_TICKET_INFO, "contribution_message": "응원합니다"},
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert _attr(response) == "ticket_info"


@pytest.mark.django_db
def test_cart_add_contribution_message_allowed_for_donation_ticket(customer_client, customer_user, donation_product):
    response = CartProductsApi(http_client=customer_client).create(
        {
            "product": str(donation_product.id),
            "options": [],
            "ticket_info": {**VALID_TICKET_INFO, "contribution_message": "응원합니다"},
        }
    )
    assert response.status_code == HTTP_201_CREATED
    opr = OrderProductRelation.objects.get(product=donation_product, order__user=customer_user)
    assert TicketInfo.objects.get(order_product_relation=opr).contribution_message == "응원합니다"


# ==================== 결제 직전(CHECKOUT_CART) 검증 — CartOrderableCheckSerializer ====================


@pytest.mark.django_db
def test_checkout_rejects_ticket_cart_without_ticket_info(customer_client, order_factory):
    order_factory(status="cart")  # 티켓 OPR, ticket_info 없음.
    response = OrdersApi(http_client=customer_client).create(
        {"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_checkout_allows_ticket_cart_with_ticket_info(customer_client, order_factory, mock_portone_register):
    cart = order_factory(status="cart")
    TicketInfo.objects.create(order_product_relation=cart.products.get(), **VALID_TICKET_INFO)
    response = OrdersApi(http_client=customer_client).create(
        {"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""}
    )
    assert response.status_code == HTTP_201_CREATED


# ==================== 통합 수정 PATCH — OrderProductViewSet.partial_update ====================


@pytest.mark.django_db
def test_patch_sets_ticket_info_on_ticket_opr(customer_client, ticket_opr):
    response = OrderProductsApi(http_client=customer_client).update(
        ticket_opr.order_id, ticket_opr.id, {"ticket_info": VALID_TICKET_INFO}
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    assert TicketInfo.objects.get(order_product_relation=ticket_opr).name == VALID_TICKET_INFO["name"]


@pytest.mark.django_db
def test_patch_updates_existing_ticket_info(customer_client, ticket_opr):
    TicketInfo.objects.create(order_product_relation=ticket_opr, **VALID_TICKET_INFO)
    api = OrderProductsApi(http_client=customer_client)
    response = api.update(ticket_opr.order_id, ticket_opr.id, {"ticket_info": {**VALID_TICKET_INFO, "name": "이수정"}})
    assert response.status_code == HTTP_204_NO_CONTENT
    assert TicketInfo.objects.filter(order_product_relation=ticket_opr).count() == 1
    assert TicketInfo.objects.get(order_product_relation=ticket_opr).name == "이수정"


@pytest.mark.django_db
def test_patch_rejects_ticket_info_on_non_ticket_opr(customer_client, non_ticket_opr):
    response = OrderProductsApi(http_client=customer_client).update(
        non_ticket_opr.order_id, non_ticket_opr.id, {"ticket_info": VALID_TICKET_INFO}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert _attr(response) == "ticket_info"
    assert not TicketInfo.objects.filter(order_product_relation=non_ticket_opr).exists()


@pytest.mark.django_db
def test_patch_rejects_contribution_message_on_non_donation_ticket(customer_client, ticket_opr):
    # ticket_opr 상품은 donation_allowed=False (order_factory donation=0) → contribution_message 거부.
    response = OrderProductsApi(http_client=customer_client).update(
        ticket_opr.order_id, ticket_opr.id, {"ticket_info": {**VALID_TICKET_INFO, "contribution_message": "응원"}}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert _attr(response) == "ticket_info"


@pytest.mark.django_db
def test_patch_validates_ticket_info_phone(customer_client, ticket_opr):
    response = OrderProductsApi(http_client=customer_client).update(
        ticket_opr.order_id, ticket_opr.id, {"ticket_info": {**VALID_TICKET_INFO, "phone": "not-a-phone"}}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_patch_modifies_option_custom_response(customer_client, modifiable_option_relation):
    opr = modifiable_option_relation.order_product_relation
    response = OrderProductsApi(http_client=customer_client).update(
        opr.order_id,
        opr.id,
        {
            "options": [
                {"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "수정됨"}
            ]
        },
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response == "수정됨"


@pytest.mark.django_db
def test_patch_applies_options_and_ticket_info_together(customer_client, modifiable_option_relation):
    opr = modifiable_option_relation.order_product_relation
    response = OrderProductsApi(http_client=customer_client).update(
        opr.order_id,
        opr.id,
        {
            "ticket_info": VALID_TICKET_INFO,
            "options": [
                {"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "둘다"}
            ],
        },
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    modifiable_option_relation.refresh_from_db()
    assert modifiable_option_relation.custom_response == "둘다"
    assert TicketInfo.objects.filter(order_product_relation=opr, name=VALID_TICKET_INFO["name"]).exists()


@pytest.mark.django_db
def test_patch_rejects_other_users_opr(other_client, ticket_opr):
    response = OrderProductsApi(http_client=other_client).update(
        ticket_opr.order_id, ticket_opr.id, {"ticket_info": VALID_TICKET_INFO}
    )
    assert response.status_code == HTTP_404_NOT_FOUND


# ==================== 읽기 노출 — OrderDto.products[].ticket_info ====================


@pytest.mark.django_db
def test_order_dto_exposes_ticket_info(customer_client, ticket_opr):
    TicketInfo.objects.create(order_product_relation=ticket_opr, **VALID_TICKET_INFO, contribution_message="응원")
    response = OrdersApi(http_client=customer_client).retrieve(ticket_opr.order_id)
    assert response.status_code == HTTP_200_OK
    product_dto = next(p for p in response.json()["products"] if p["id"] == str(ticket_opr.id))
    assert product_dto["ticket_info"] == {**VALID_TICKET_INFO, "contribution_message": "응원"}


@pytest.mark.django_db
def test_order_dto_ticket_info_null_when_absent(customer_client, ticket_opr):
    response = OrdersApi(http_client=customer_client).retrieve(ticket_opr.order_id)
    assert response.status_code == HTTP_200_OK
    product_dto = next(p for p in response.json()["products"] if p["id"] == str(ticket_opr.id))
    assert product_dto["ticket_info"] is None
