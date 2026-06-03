"""Admin 상품 등록 → 고객 결제 → 환불 까지의 전체 플로우 E2E. UserExt 외에는 빈 DB 에서 시작."""

from unittest.mock import call

import pytest
from core.const.shop_error_messages import NotRefundableErrorMessages
from django.test import override_settings
from rest_framework.fields import DateTimeField
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT
from shop.conftest import FAR_FUTURE, FAR_PAST, WEBHOOK_WHITELISTED_IP
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistoryStatus
from shop.test.helpers import (
    CartApi,
    CartProductsApi,
    CategoryGroupsAdminApi,
    OptionGroupsAdminApi,
    OrderProductsApi,
    OrdersApi,
    PortOneWebhookApi,
    ProductsAdminApi,
    make_portone_payment_info,
)


@pytest.fixture
def created_product(staff_client) -> dict:
    """Admin 이 카테고리·상품·옵션그룹(사이즈+요청사항) 까지 등록 — 후속 고객 플로우의 setup."""
    cg_response = CategoryGroupsAdminApi(http_client=staff_client).create(
        {"name": "굿즈", "priority": 0, "categories": [{"name": "티셔츠", "priority": 0}]}
    )
    assert cg_response.status_code == HTTP_201_CREATED
    category_id = cg_response.json()["categories"][0]["id"]

    product_response = ProductsAdminApi(http_client=staff_client).create(
        {
            "name_ko": "파이콘 티셔츠",
            "name_en": "PyCon T-shirt",
            "price": 25000,
            "stock": 100,
            "visible_starts_at": FAR_PAST.isoformat(),
            "visible_ends_at": FAR_FUTURE.isoformat(),
            "orderable_starts_at": FAR_PAST.isoformat(),
            "orderable_ends_at": FAR_FUTURE.isoformat(),
            "refundable_ends_at": FAR_FUTURE.isoformat(),
            "category": category_id,
        }
    )
    assert product_response.status_code == HTTP_201_CREATED
    product_id = product_response.json()["id"]

    # 사이즈 옵션 그룹 (select 형, 필수 1개).
    size_group_response = OptionGroupsAdminApi(http_client=staff_client).create(
        {
            "product": product_id,
            "name_ko": "사이즈",
            "name_en": "Size",
            "min_quantity_per_product": 1,
            "max_quantity_per_product": 1,
            "is_custom_response": False,
            "options": [
                {"name_ko": "S", "name_en": "S", "additional_price": 0, "stock": 0},
                {"name_ko": "M", "name_en": "M", "additional_price": 0, "stock": 0},
                {"name_ko": "L", "name_en": "L", "additional_price": 1000, "stock": 0},
            ],
        }
    )
    assert size_group_response.status_code == HTTP_201_CREATED
    size_group_body = size_group_response.json()
    size_options_by_name = {o["name_ko"]: o["id"] for o in size_group_body["options"]}

    # 요청사항 옵션 그룹 (custom_response 형).
    custom_group_response = OptionGroupsAdminApi(http_client=staff_client).create(
        {
            "product": product_id,
            "name_ko": "요청사항",
            "name_en": "Request",
            "is_custom_response": True,
            "custom_response_pattern": r"^.{1,100}$",
        }
    )
    assert custom_group_response.status_code == HTTP_201_CREATED

    return {
        "product_id": product_id,
        "size_group_id": size_group_body["id"],
        "size_options": size_options_by_name,
        "custom_group_id": custom_group_response.json()["id"],
    }


@pytest.mark.django_db
def test_single_product_cart_full_flow_admin_setup_purchase_refund(
    customer_client,
    customer_user,
    anon_client,
    created_product,
    mock_portone_register,
    mock_portone_find_payment_info,
    mock_portone_req_cancel_payment,
):
    # 1. 고객이 SingleProductCart 로 단건 결제 시작.
    create_response = OrdersApi(http_client=customer_client).create_single(
        {
            "product": created_product["product_id"],
            "options": [
                {
                    "product_option_group": created_product["size_group_id"],
                    "product_option": created_product["size_options"]["M"],
                    "custom_response": None,
                },
                {
                    "product_option_group": created_product["custom_group_id"],
                    "product_option": None,
                    "custom_response": "배송 빠르게 부탁드려요",
                },
            ],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "customer@example.com",
                "organization": "",
            },
        }
    )
    assert create_response.status_code == HTTP_201_CREATED
    cart = SingleProductCart.objects.get(user=customer_user)
    mock_portone_register.assert_called_once_with(merchant_id=cart.merchant_uid, price=cart.first_paid_price)

    # 2. PortOne 결제 완료 webhook 도착 → cart 가 Order 로 promote.
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=cart)
    webhook_response = PortOneWebhookApi(http_client=anon_client).notify(
        merchant_uid=cart.merchant_uid, ip=WEBHOOK_WHITELISTED_IP
    )
    assert webhook_response.status_code == HTTP_200_OK

    order = Order.objects.get(id=cart.id)
    assert not SingleProductCart.objects.filter(id=cart.id).exists()  # hard_delete 됨.
    assert order.current_status == PaymentHistoryStatus.completed
    assert order.first_paid_price == 25000

    # 3. 고객이 주문 전체 환불 요청 (단일 OPR 이라 부분 환불은 전체 환불과 동치).
    delete_response = OrdersApi(http_client=customer_client).delete(order.id)
    assert delete_response.status_code == HTTP_204_NO_CONTENT
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id=order.latest_imp_id, refund_request_price=25000, current_leftover_price=25000
    )
    # cached_property 무효화 위해 재조회.
    refreshed = Order.objects.get(id=order.id)
    assert list(refreshed.products.values_list("status", flat=True)) == [
        OrderProductRelation.OrderProductStatus.refunded
    ]
    assert refreshed.current_status == PaymentHistoryStatus.refunded


@pytest.mark.django_db
def test_order_cart_full_flow_admin_setup_two_oprs_partial_then_full_refund(
    customer_client,
    customer_user,
    anon_client,
    created_product,
    mock_portone_register,
    mock_portone_find_payment_info,
    mock_portone_req_cancel_payment,
):
    # 1. 고객이 cart 에 같은 상품을 사이즈만 다르게 2건 담음.
    cart_products = CartProductsApi(http_client=customer_client)
    add_first = cart_products.create(
        {
            "product": created_product["product_id"],
            "options": [
                {
                    "product_option_group": created_product["size_group_id"],
                    "product_option": created_product["size_options"]["S"],
                    "custom_response": None,
                },
                {
                    "product_option_group": created_product["custom_group_id"],
                    "product_option": None,
                    "custom_response": "첫 번째",
                },
            ],
        }
    )
    assert add_first.status_code == HTTP_201_CREATED
    add_second = cart_products.create(
        {
            "product": created_product["product_id"],
            "options": [
                {
                    "product_option_group": created_product["size_group_id"],
                    "product_option": created_product["size_options"]["L"],
                    "custom_response": None,
                },
                {
                    "product_option_group": created_product["custom_group_id"],
                    "product_option": None,
                    "custom_response": "두 번째",
                },
            ],
        }
    )
    assert add_second.status_code == HTTP_201_CREATED

    cart = Order.objects.get(user=customer_user)
    assert cart.products.count() == 2

    # 2. 결제 시작 — customer_info 저장 + PortOne 사전 등록 호출.
    checkout_response = OrdersApi(http_client=customer_client).create(
        {"name": "홍길동", "phone": "010-1234-5678", "email": "customer@example.com", "organization": ""}
    )
    assert checkout_response.status_code == HTTP_201_CREATED
    assert CustomerInfo.objects.filter(order=cart, name="홍길동").exists()
    cart.refresh_from_db()

    # 3. PortOne 결제 완료 webhook 도착.
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=cart)
    webhook_response = PortOneWebhookApi(http_client=anon_client).notify(
        merchant_uid=cart.merchant_uid, ip=WEBHOOK_WHITELISTED_IP
    )
    assert webhook_response.status_code == HTTP_200_OK
    refreshed = Order.objects.get(id=cart.id)
    assert refreshed.current_status == PaymentHistoryStatus.completed
    # L 옵션 (+1000) 1건 + S (+0) 1건 → 25000 * 2 + 1000 = 51000.
    assert refreshed.first_paid_price == 51000

    # 4. 첫 번째 OPR 만 부분 환불 — 남은 1건 paid → PaymentHistory partial_refunded.
    first_opr, second_opr = list(refreshed.products.order_by("created_at"))
    partial_response = OrderProductsApi(http_client=customer_client).delete_partial(refreshed.id, first_opr.id)
    assert partial_response.status_code == HTTP_204_NO_CONTENT
    first_opr.refresh_from_db()
    second_opr.refresh_from_db()
    assert first_opr.status == OrderProductRelation.OrderProductStatus.refunded
    assert second_opr.status == OrderProductRelation.OrderProductStatus.paid
    assert Order.objects.get(id=cart.id).current_status == PaymentHistoryStatus.partial_refunded

    # 5. 남은 OPR 전액 환불 — refunded 로 종료.
    full_response = OrdersApi(http_client=customer_client).delete(cart.id)
    assert full_response.status_code == HTTP_204_NO_CONTENT
    final = Order.objects.get(id=cart.id)
    assert final.current_status == PaymentHistoryStatus.refunded
    assert list(final.products.order_by("created_at").values_list("status", flat=True)) == [
        OrderProductRelation.OrderProductStatus.refunded,
        OrderProductRelation.OrderProductStatus.refunded,
    ]
    # PortOne 취소 호출 두 번의 인자 + 순서 + 횟수까지 strict 검증:
    #   (1) 부분 환불 = S OPR(25000), 호출 시점 leftover = 51000
    #   (2) 전체 환불 = 남은 L OPR(26000 = 25000 + 옵션 1000), leftover = 26000
    assert mock_portone_req_cancel_payment.call_args_list == [
        call(imp_id=refreshed.latest_imp_id, refund_request_price=25000, current_leftover_price=51000),
        call(imp_id=refreshed.latest_imp_id, refund_request_price=26000, current_leftover_price=26000),
    ]


_TEST_BACKEND_DOMAIN = "https://test.pycon.kr"


@override_settings(BACKEND_DOMAIN=_TEST_BACKEND_DOMAIN)
@pytest.mark.django_db
def test_cart_get_reflects_added_products_for_e2e_setup(customer_client, customer_user, created_product):
    # cart 조회가 admin 이 만든 product / option group nested 데이터를 OrderDto 의 모든 필드로 노출.
    CartProductsApi(http_client=customer_client).create(
        {
            "product": created_product["product_id"],
            "options": [
                {
                    "product_option_group": created_product["size_group_id"],
                    "product_option": created_product["size_options"]["M"],
                    "custom_response": None,
                },
                {
                    "product_option_group": created_product["custom_group_id"],
                    "product_option": None,
                    "custom_response": "안녕",
                },
            ],
        }
    )
    cart_response = CartApi(http_client=customer_client).list()
    assert cart_response.status_code == HTTP_200_OK

    cart = Order.objects.get(user=customer_user)
    opr = cart.products.get()
    size_opor = opr.options.get(product_option_group_id=created_product["size_group_id"])
    custom_opor = opr.options.get(product_option_group_id=created_product["custom_group_id"])

    assert cart_response.json() == {
        "id": str(cart.id),
        "name": cart.name,
        "payment_histories": [],
        "products": [
            {
                "id": str(opr.id),
                "product": {
                    "id": created_product["product_id"],
                    "name": "파이콘 티셔츠",
                    "price": 25000,
                    "image": None,
                },
                "options": [
                    {
                        "id": str(size_opor.id),
                        "product_option": {
                            "id": created_product["size_options"]["M"],
                            "name": "M",
                            "additional_price": 0,
                        },
                        "product_option_group": {
                            "id": created_product["size_group_id"],
                            "name": "사이즈",
                            "is_custom_response": False,
                            "custom_response_pattern": None,
                            "response_modifiable_ends_at": None,
                        },
                        "custom_response": None,
                    },
                    {
                        "id": str(custom_opor.id),
                        "product_option": None,
                        "product_option_group": {
                            "id": created_product["custom_group_id"],
                            "name": "요청사항",
                            "is_custom_response": True,
                            "custom_response_pattern": r"^.{1,100}$",
                            "response_modifiable_ends_at": None,
                        },
                        "custom_response": "안녕",
                    },
                ],
                "status": OrderProductRelation.OrderProductStatus.pending,
                "price": 25000,
                "donation_price": 0,
                # 카테고리 "티셔츠" — is_ticket=False → scancode_url None.
                "not_refundable_reason": NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE,
                "scancode_url": None,
            },
        ],
        "scancode_url": f"{_TEST_BACKEND_DOMAIN}{cart.scancode_path}",
        "first_paid_price": 25000,
        "first_paid_at": None,
        "current_paid_price": 0,
        "current_status": PaymentHistoryStatus.pending,
        "created_at": DateTimeField().to_representation(cart.created_at),
        "not_fully_refundable_reason": NotRefundableErrorMessages.ORDER_IMP_ID_NOT_EXIST,
        "customer_info": None,
        "merchant_uid": None,
    }
