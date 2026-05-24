"""FIXME #2: order aggregate 의 모든 접근 경로가 soft-deleted row 를 제외해야 한다.

`BaseAbstractModelQuerySet` 의 기본 매니저는 deleted_at 을 자동 필터하지 않는다 — `.filter_active()`
가 opt-in 이라 reverse manager (`.products`, `.options`, `.payment_histories`) 의 `.all()` 은
soft-deleted row 를 그대로 노출한다. 본 모듈은 결제 계산 / DTO / export 가 active row 만 본다는
계약을 회귀 테스트로 고정한다.
"""

import pytest
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND
from rest_framework.test import APIClient
from shop.conftest import WEBHOOK_WHITELISTED_IP
from shop.order.exports import OrderProductExportSerializer
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import OptionGroup
from shop.serializers.refund import OrderProductRefundSerializer
from shop.test.helpers import make_portone_payment_info, make_webhook_payload

# ---------- 1. Model-level: first_paid_price / refundable reason ----------


@pytest.mark.django_db
def test_first_paid_price_excludes_soft_deleted_opr(order_factory, product):
    """OPR 두 건 중 하나 soft-delete → first_paid_price 는 남은 active OPR 만 합산."""
    order = order_factory()
    keep = order.products.first()
    extra = OrderProductRelation.objects.create(order=order, product=product, price=7777, donation_price=1111)

    extra.delete()

    refreshed = Order.objects.get(id=order.id)
    assert refreshed.first_paid_price == keep.price + keep.donation_price


@pytest.mark.django_db
def test_not_fully_refundable_reason_ignores_soft_deleted_opr(order_factory, product):
    """soft-deleted paid OPR 은 refund target / expected_refund_price 계산에서 제외 — invariant 깨지지 않음."""
    completed = order_factory(status="completed")
    stale = OrderProductRelation.objects.create(
        order=completed,
        product=product,
        price=99999,
        donation_price=0,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale.delete()

    refreshed = Order.objects.get(id=completed.id)
    assert refreshed.not_fully_refundable_reason is None


# ---------- 2. PaymentHistory: current/first 계산이 soft-deleted PH 제외 ----------


@pytest.mark.django_db
def test_current_payment_history_excludes_soft_deleted(order_factory):
    """refunded PH 를 soft-delete 하면 current_status 는 다시 completed."""
    completed = order_factory(status="refunded")
    refund_ph = completed.payment_histories.order_by("-created_at").first()
    assert refund_ph.status == PaymentHistoryStatus.refunded

    refund_ph.delete()

    refreshed = Order.objects.get(id=completed.id)
    assert refreshed.current_status == PaymentHistoryStatus.completed
    assert refreshed.first_payment_history.id != refund_ph.id


@pytest.mark.django_db
def test_prefetched_payment_history_accessors_exclude_soft_deleted(order_factory):
    """Order.prefetchs 의 filter_active 가 prefetched 경로에서도 soft-deleted PH 를 숨긴다."""
    completed = order_factory(status="refunded")
    refund_ph = completed.payment_histories.order_by("-created_at").first()
    refund_ph.delete()

    prefetched = Order.objects.prefetch_related(Order.prefetchs["_active_payment_histories"]).get(id=completed.id)
    assert prefetched.current_status == PaymentHistoryStatus.completed
    assert all(ph.id != refund_ph.id for ph in prefetched._active_payment_histories)


# ---------- 3. DTO: list/retrieve/checkout 응답에서 제외 ----------


@pytest.mark.django_db
def test_order_retrieve_dto_excludes_soft_deleted_opr_and_options(customer_client, order_factory, product):
    """retrieve 응답의 products 배열에 soft-deleted OPR / option 이 노출되지 않는다."""
    completed = order_factory(status="completed")
    keep_opr = completed.products.first()
    keep_group = OptionGroup.objects.create(product=product, name="활성옵션")
    keep_option = OrderProductOptionRelation.objects.create(
        order_product_relation=keep_opr, product_option_group=keep_group, custom_response="alive"
    )
    stale_group = OptionGroup.objects.create(product=product, name="삭제옵션")
    stale_option = OrderProductOptionRelation.objects.create(
        order_product_relation=keep_opr, product_option_group=stale_group, custom_response="dead"
    )
    stale_option.delete()

    stale_opr = OrderProductRelation.objects.create(
        order=completed,
        product=product,
        price=12345,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale_opr.delete()

    response = customer_client.get(reverse("v1:orders-detail", kwargs={"order_id": completed.id}))
    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert {p["id"] for p in body["products"]} == {str(keep_opr.id)}
    options = next(p["options"] for p in body["products"] if p["id"] == str(keep_opr.id))
    assert {o["id"] for o in options} == {str(keep_option.id)}


@pytest.mark.django_db
def test_order_retrieve_dto_excludes_soft_deleted_payment_history(customer_client, order_factory):
    """retrieve 응답의 payment_histories 에 soft-deleted PH 가 포함되지 않는다."""
    completed = order_factory(status="refunded")
    refund_ph = completed.payment_histories.order_by("-created_at").first()
    refund_ph.delete()

    response = customer_client.get(reverse("v1:orders-detail", kwargs={"order_id": completed.id}))
    assert response.status_code == HTTP_200_OK
    statuses = {ph["status"] for ph in response.json()["payment_histories"]}
    assert PaymentHistoryStatus.refunded not in statuses
    assert PaymentHistoryStatus.completed in statuses


@pytest.mark.django_db
def test_checkout_response_dto_excludes_soft_deleted_rows(
    customer_client, order_factory, product, mock_portone_register
):
    """checkout (POST /shop/orders/) 응답에 soft-deleted OPR 가 노출되지 않는다."""
    cart = order_factory(status="cart")
    stale_opr = OrderProductRelation.objects.create(order=cart, product=product, price=99999)
    stale_opr.delete()

    response = customer_client.post(
        reverse("v1:orders-list"),
        data={"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""},
        format="json",
    )
    assert response.status_code == HTTP_201_CREATED, response.content
    body = response.json()
    assert all(p["id"] != str(stale_opr.id) for p in body["products"])
    assert body["first_paid_price"] == product.price


# ---------- 4. Webhook: paid 전환이 soft-deleted OPR 를 건너뜀 ----------


@pytest.mark.django_db
def test_webhook_paid_transition_skips_soft_deleted_opr(mock_portone_find_payment_info, order_factory, product):
    """webhook PAID 처리 시 soft-deleted OPR 는 paid 로 전환되지 않고 deleted 상태가 유지된다."""
    order = order_factory(status="cart")
    active_opr = order.products.get()
    stale_opr = OrderProductRelation.objects.create(order=order, product=product, price=product.price)
    stale_opr.delete()
    order.prepare_payment()

    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=order)
    response = APIClient().post(
        path=reverse("v1:payment_histories-list"),
        data=make_webhook_payload(merchant_uid=order.merchant_uid, status="paid", imp_uid="imp_x"),
        format="json",
        REMOTE_ADDR=WEBHOOK_WHITELISTED_IP,
    )
    assert response.status_code == HTTP_200_OK, response.content

    active_opr.refresh_from_db()
    stale_opr.refresh_from_db()
    assert active_opr.status == OrderProductRelation.OrderProductStatus.paid
    assert stale_opr.status == OrderProductRelation.OrderProductStatus.pending
    assert stale_opr.deleted_at is not None


# ---------- 5. Export: options.all() leak ----------


@pytest.mark.django_db
def test_order_product_export_excludes_soft_deleted_options(order_factory, product):
    """관리자 export 의 OrderProductExportSerializer.to_representation 이 soft-deleted option 을 행에 포함시키지 않는다."""
    completed = order_factory(status="completed")
    opr = completed.products.first()
    keep_group = OptionGroup.objects.create(product=product, name="활성그룹", is_custom_response=True)
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=keep_group, custom_response="alive"
    )
    stale_group = OptionGroup.objects.create(product=product, name="삭제그룹", is_custom_response=True)
    stale_option = OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=stale_group, custom_response="dead"
    )
    stale_option.delete()

    df = OrderProductExportSerializer(instance=OrderProductRelation.objects.filter(id=opr.id), many=True).export()
    assert df.iloc[0]["활성그룹"] == "alive"
    assert "삭제그룹" not in df.columns


# ---------- 6. Refund: partial vs full status check ignores soft-deleted ----------


@pytest.mark.django_db
def test_partial_refund_status_check_ignores_soft_deleted_opr(order_factory, mock_portone_req_cancel_payment, product):
    """부분 환불 직후 partial/full 분기 — soft-deleted paid OPR 가 남아있어도 full refund 로 인식돼야 한다."""
    completed = order_factory(status="completed")
    target_opr = completed.products.first()

    stale = OrderProductRelation.objects.create(
        order=completed,
        product=product,
        price=1,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale.delete()

    serializer = OrderProductRefundSerializer(instance=target_opr, data={}, context={"check_totp": False})
    serializer.is_valid(raise_exception=True)
    serializer.refund()

    latest_ph = PaymentHistory.objects.filter(order=completed).order_by("-created_at").first()
    assert latest_ph.status == PaymentHistoryStatus.refunded


# ---------- 7. QuerySet helpers: PaymentHistory Exists 가 soft-deleted PH 제외 ----------


@pytest.mark.django_db
def test_filter_has_payment_histories_ignores_soft_deleted_ph(order_factory):
    """완료 주문의 모든 PH 가 soft-deleted 면 `filter_has_payment_histories` 는 그 주문을 제외해야 한다."""
    completed = order_factory(status="completed")
    other = order_factory(status="completed")
    for ph in completed.payment_histories.all():
        ph.delete()

    has_ph_ids = set(Order.objects.filter_has_payment_histories().values_list("id", flat=True))
    no_ph_ids = set(Order.objects.filter_has_no_payment_histories().values_list("id", flat=True))
    assert other.id in has_ph_ids
    assert completed.id not in has_ph_ids
    assert completed.id in no_ph_ids


# ---------- 8. CartViewSet.list DTO 가 soft-deleted 를 가리는지 ----------


@pytest.mark.django_db
def test_cart_list_dto_excludes_soft_deleted_opr_and_options(customer_client, order_factory, product):
    """장바구니 조회 응답이 soft-deleted OPR / option 을 노출하지 않는다."""
    cart = order_factory(status="cart")
    active_opr = cart.products.get()
    active_group = OptionGroup.objects.create(product=product, name="활성옵션")
    active_option = OrderProductOptionRelation.objects.create(
        order_product_relation=active_opr, product_option_group=active_group, custom_response="alive"
    )
    stale_group = OptionGroup.objects.create(product=product, name="삭제옵션")
    stale_option = OrderProductOptionRelation.objects.create(
        order_product_relation=active_opr, product_option_group=stale_group, custom_response="dead"
    )
    stale_option.delete()
    stale_opr = OrderProductRelation.objects.create(order=cart, product=product, price=99999)
    stale_opr.delete()

    response = customer_client.get(reverse("v1:cart-list"))
    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert {p["id"] for p in body["products"]} == {str(active_opr.id)}
    options = next(p["options"] for p in body["products"] if p["id"] == str(active_opr.id))
    assert {o["id"] for o in options} == {str(active_option.id)}


# ---------- 9. OrderProductViewSet — modify_options 응답 & 부분 환불 lookup ----------


@pytest.mark.django_db
def test_modify_options_response_dto_excludes_soft_deleted_sibling(
    customer_client, order_factory, modifiable_option_relation, product
):
    """modify_options 응답의 products[] 가 soft-deleted sibling OPR 을 노출하지 않는다."""
    completed = modifiable_option_relation.order_product_relation.order
    stale_opr = OrderProductRelation.objects.create(
        order=completed, product=product, price=12345, status=OrderProductRelation.OrderProductStatus.paid
    )
    stale_opr.delete()

    response = customer_client.patch(
        reverse(
            "v1:order-products-modify-options",
            kwargs={
                "order_id": completed.id,
                "order_product_rel_id": modifiable_option_relation.order_product_relation_id,
            },
        ),
        data=[{"order_product_option_relation": str(modifiable_option_relation.id), "custom_response": "수정"}],
        format="json",
    )
    assert response.status_code == HTTP_200_OK, response.content
    assert all(p["id"] != str(stale_opr.id) for p in response.json()["products"])


@pytest.mark.django_db
def test_user_partial_refund_returns_404_for_soft_deleted_opr(customer_client, order_factory, product):
    """soft-deleted paid OPR 에 대한 부분 환불 DELETE 는 get_queryset 에서 제외돼 404."""
    completed = order_factory(status="completed")
    stale_opr = OrderProductRelation.objects.create(
        order=completed, product=product, price=12345, status=OrderProductRelation.OrderProductStatus.paid
    )
    stale_opr.delete()

    response = customer_client.delete(
        reverse(
            "v1:order-products-detail",
            kwargs={"order_id": completed.id, "order_product_rel_id": stale_opr.id},
        )
    )
    assert response.status_code == HTTP_404_NOT_FOUND


# ---------- 10. CartProductViewSet — soft-deleted OPR 재삭제 시도는 404 ----------


@pytest.mark.django_db
def test_cart_product_delete_404_for_already_soft_deleted_opr(customer_client, order_factory):
    """이미 soft-deleted 된 cart OPR 은 get_queryset 에서 제외돼 두 번째 DELETE 는 404."""
    cart = order_factory(status="cart")
    opr = cart.products.get()
    opr.delete()

    response = customer_client.delete(reverse("v1:cart-products-detail", kwargs={"order_product_rel_id": opr.id}))
    assert response.status_code == HTTP_404_NOT_FOUND
