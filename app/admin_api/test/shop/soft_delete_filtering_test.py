"""Admin shop API soft-delete 회귀 — export / 부분 환불 lookup / list filter 가 soft-deleted row 를 노출하지 않는다."""

from datetime import datetime, timezone
from io import BytesIO

import pandas
import pytest
from freezegun import freeze_time
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Product
from shop.test.helpers import OrdersAdminApi, valid_refund_totp


@pytest.mark.django_db
def test_admin_refund_product_404_for_soft_deleted_opr(api_client, order_factory, ticket_product):
    """soft-deleted paid OPR 은 admin refund_product 에서 lookup 되지 않아 404."""
    completed = order_factory(status="completed")
    stale_opr = OrderProductRelation.objects.create(
        order=completed,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale_opr.delete()

    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed.id, stale_opr.id, totp=valid_refund_totp()
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@freeze_time(datetime(2026, 5, 23, 15, 30, 45, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_admin_export_excludes_soft_deleted_opr_from_product_sheet(api_client, order_factory, ticket_product):
    """admin export 의 '주문상품' 시트에 soft-deleted OPR 가 들어가지 않는다."""
    completed = order_factory(status="completed")
    active_opr = completed.products.get()
    stale_opr = OrderProductRelation.objects.create(
        order=completed,
        product=ticket_product,
        price=99999,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale_opr.delete()

    response = OrdersAdminApi(http_client=api_client).export(
        {"product_ids": [str(ticket_product.id)], "include_refunded": False}
    )
    assert response.status_code == HTTP_200_OK
    df_dict = pandas.read_excel(
        BytesIO(b"".join(response.streaming_content)),
        sheet_name="주문상품",
        index_col=0,
        na_filter=False,
        dtype={"고객 전화번호": str, "PortOne ID": str},
    )
    rows = df_dict.to_dict(orient="records")
    prices = {row["결제 금액"] for row in rows}
    assert active_opr.price in prices  # 활성 OPR row 가 존재
    assert 99999 not in prices  # soft-deleted OPR(price=99999) 는 시트에 없음
    assert str(completed.id) in {row["주문 번호"] for row in rows}


@freeze_time(datetime(2026, 5, 23, 15, 30, 45, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_admin_export_excludes_order_with_only_soft_deleted_matching_opr(
    api_client, customer_user, ticket_product, order_factory
):
    """선택 product_id 가 soft-deleted OPR 에만 있는 주문은 export 양쪽 시트 모두에서 제외돼야 한다."""
    target_product = ticket_product

    # 1) 활성 OPR 가 있는 정상 주문 — export 대상.
    normal = order_factory(status="completed")

    # 2) 같은 ticket_product 로 soft-deleted OPR 만 가진 주문 (다른 ticket_product 의 paid OPR 보유) — export 에서 빠져야.
    other_product = Product.objects.create(
        category=target_product.category,
        name="기타",
        price=500,
        visible_starts_at=target_product.visible_starts_at,
        visible_ends_at=target_product.visible_ends_at,
        orderable_starts_at=target_product.orderable_starts_at,
        orderable_ends_at=target_product.orderable_ends_at,
        refundable_ends_at=target_product.refundable_ends_at,
    )
    leak_candidate = Order.objects.create(user=customer_user, name="leak")
    OrderProductRelation.objects.create(
        order=leak_candidate,
        product=other_product,
        price=500,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale = OrderProductRelation.objects.create(
        order=leak_candidate,
        product=target_product,
        price=99999,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale.delete()
    # leak_candidate 도 완료 PH 가 있어야 current_status filter 를 통과 — 그래야 누수 가능성이 노출됨.
    PaymentHistory.objects.create(order=leak_candidate, imp_id="leak", status=PaymentHistoryStatus.completed, price=500)

    response = OrdersAdminApi(http_client=api_client).export(
        {"product_ids": [str(target_product.id)], "include_refunded": True}
    )
    assert response.status_code == HTTP_200_OK
    df_dict = pandas.read_excel(
        BytesIO(b"".join(response.streaming_content)),
        sheet_name=None,
        index_col=0,
        na_filter=False,
        dtype={"고객 전화번호": str, "PortOne ID": str},
    )
    order_ids = {row["주문 번호"] for row in df_dict["주문"].to_dict(orient="records")}
    assert str(normal.id) in order_ids
    assert str(leak_candidate.id) not in order_ids


@pytest.mark.django_db
def test_admin_list_filter_by_product_id_ignores_soft_deleted_opr(
    api_client, customer_user, ticket_product, order_factory
):
    """`?product_id=` 필터가 soft-deleted OPR 만 가진 주문을 매칭하지 않는다."""
    matching_order = order_factory(status="completed")

    other_product = Product.objects.create(
        category=ticket_product.category,
        name="기타2",
        price=500,
        visible_starts_at=ticket_product.visible_starts_at,
        visible_ends_at=ticket_product.visible_ends_at,
        orderable_starts_at=ticket_product.orderable_starts_at,
        orderable_ends_at=ticket_product.orderable_ends_at,
        refundable_ends_at=ticket_product.refundable_ends_at,
    )
    leak_candidate = Order.objects.create(user=customer_user, name="leak")
    OrderProductRelation.objects.create(
        order=leak_candidate,
        product=other_product,
        price=500,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    stale = OrderProductRelation.objects.create(
        order=leak_candidate, product=ticket_product, price=99999, status=OrderProductRelation.OrderProductStatus.paid
    )
    stale.delete()
    PaymentHistory.objects.create(order=leak_candidate, imp_id="leak", status=PaymentHistoryStatus.completed, price=500)

    response = OrdersAdminApi(http_client=api_client).list({"product_id": str(ticket_product.id)})
    assert response.status_code == HTTP_200_OK
    returned_ids = {row["id"] for row in response.json()["results"]}
    assert str(matching_order.id) in returned_ids
    assert str(leak_candidate.id) not in returned_ids
