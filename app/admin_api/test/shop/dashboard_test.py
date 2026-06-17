from datetime import datetime

import pytest
from core.const.datetime import KST
from django.urls import reverse
from freezegun import freeze_time
from model_bakery import baker
from rest_framework import status
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory
from shop.product.models import Category, CategoryGroup, Product

CHARTS_URL = reverse("v1:admin-dashboard-chart-list")

S = OrderProductRelation.OrderProductStatus


def _data_url(chart_id):
    return reverse("v1:admin-dashboard-chart-data", kwargs={"pk": chart_id})


def _chart_data(api_client, chart_id, params=None):
    return api_client.post(_data_url(chart_id), {"params": params or {}}, format="json")


@pytest.fixture
def make_opr(customer_user):
    """주어진 상품/상태의 OrderProductRelation 을 즉석 생성 (PaymentHistory 없이 상태만 세팅)."""

    def _make(product, opr_status, *, price=None, donation=0) -> OrderProductRelation:
        order = Order.objects.create(user=customer_user, name=product.name)
        return OrderProductRelation.objects.create(
            order=order,
            product=product,
            price=product.price if price is None else price,
            donation_price=donation,
            status=opr_status,
        )

    return _make


@pytest.fixture
def second_ticket_product(ticket_product) -> Product:
    """`ticket_product` 와 같은 티켓 카테고리의 두 번째 티켓 상품 — 티켓별 그룹 테스트용."""
    return Product.objects.create(
        category=ticket_product.category,
        name="튜토리얼 티켓",
        name_ko="튜토리얼 티켓",
        name_en="Tutorial Ticket",
        price=5000,
        stock=50,
        visible_starts_at=ticket_product.visible_starts_at,
        visible_ends_at=ticket_product.visible_ends_at,
        orderable_starts_at=ticket_product.orderable_starts_at,
        orderable_ends_at=ticket_product.orderable_ends_at,
        refundable_ends_at=ticket_product.refundable_ends_at,
    )


# --- 권한 ---
def test_charts_list_requires_superuser(customer_client):
    assert customer_client.get(CHARTS_URL).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_chart_data_requires_superuser(customer_client):
    resp = _chart_data(customer_client, "counter-ticket-paid-total")
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


# --- 차트 정의(목록/단건) ---
def test_charts_list_structure(api_client, ticket_product):
    charts = api_client.get(CHARTS_URL).json()

    chart_ids = {c["id"] for c in charts}
    assert chart_ids == {
        "counter-ticket-paid-total",
        "counter-ticket-refund-total",
        "counter-checkin-current",
        "counter-checkin-remaining",
        "counter-checkin-rate",
        "bar-ticket-paid-count",
        "bar-ticket-revenue",
        "line-sales-trend",
        "line-revenue-trend",
        "line-checkin-trend",
        "line-checkin-rate-trend",
    }

    # 각 차트가 자기 data 엔드포인트/메서드를 직접 들고 있음
    sales = next(c for c in charts if c["id"] == "line-sales-trend")
    assert sales["endpoint"] == _data_url("line-sales-trend")
    assert sales["method"] == "POST"

    # 티켓 셀렉트 옵션이 동적으로 채워짐
    ticket_param = next(p for p in sales["params"] if p["key"] == "ticket_ids")
    assert {o["label"] for o in ticket_param["options"]} == {ticket_product.name}

    # 내부 전용 필드(dynamic_options)는 응답에 노출되지 않음
    assert all("dynamic_options" not in p for c in charts for p in c["params"])


def test_ticket_option_carries_event_id(api_client, ticket_product):
    """이벤트→티켓 종속 필터용: 티켓 옵션이 소속 event_id 를 들고, 그 이벤트가 event 옵션에도 노출."""
    event = baker.make("event.Event", name="파이콘 한국 2026")
    ticket_product.category.event = event
    ticket_product.category.save()

    params = next(c for c in api_client.get(CHARTS_URL).json() if c["id"] == "line-sales-trend")["params"]
    ticket_opt = next(
        o for p in params if p["key"] == "ticket_ids" for o in p["options"] if o["value"] == str(ticket_product.id)
    )
    event_opt_values = {o["value"] for p in params if p["key"] == "event_id" for o in p["options"]}

    assert ticket_opt["event_id"] == str(event.id)
    assert str(event.id) in event_opt_values


# --- 카운터 ---
def test_counter_paid_and_refund_totals(api_client, make_opr, ticket_product):
    make_opr(ticket_product, S.paid)
    make_opr(ticket_product, S.used)  # used 도 판매 완료에 포함
    make_opr(ticket_product, S.refunded)
    make_opr(ticket_product, S.pending)  # 미결제는 미포함

    assert _chart_data(api_client, "counter-ticket-paid-total").json()["value"] == 2
    assert _chart_data(api_client, "counter-ticket-refund-total").json()["value"] == 1


def test_counter_checkin_metrics(api_client, make_opr, ticket_product):
    make_opr(ticket_product, S.used)
    make_opr(ticket_product, S.used)
    make_opr(ticket_product, S.paid)  # 아직 체크인 안 함

    assert _chart_data(api_client, "counter-checkin-current").json()["value"] == 2
    assert _chart_data(api_client, "counter-checkin-remaining").json()["value"] == 1
    assert _chart_data(api_client, "counter-checkin-rate").json()["value"] == pytest.approx(66.7)


def test_counter_checkin_rate_zero_when_no_sales(api_client, ticket_product):
    assert _chart_data(api_client, "counter-checkin-rate").json()["value"] == 0


def test_counter_filtered_by_ticket_ids(api_client, make_opr, ticket_product, second_ticket_product):
    make_opr(ticket_product, S.paid)
    make_opr(second_ticket_product, S.paid)
    make_opr(second_ticket_product, S.paid)

    resp = _chart_data(api_client, "counter-ticket-paid-total", {"ticket_ids": [str(second_ticket_product.id)]})
    assert resp.json()["value"] == 2


# --- 티켓별 (bar) ---
def test_bar_paid_count_per_ticket(api_client, make_opr, ticket_product, second_ticket_product):
    make_opr(ticket_product, S.paid)
    make_opr(ticket_product, S.used)
    make_opr(second_ticket_product, S.paid)

    body = _chart_data(api_client, "bar-ticket-paid-count").json()
    by_label = {d["label"]: d["values"]["count"] for d in body["data"]}
    assert by_label == {ticket_product.name: 2, second_ticket_product.name: 1}


def test_bar_revenue_gross_net(api_client, make_opr, ticket_product):
    # price 10000. 2건 판매(후원 1000 포함) + 1건 환불 → gross=31000, refund=10000, net=21000.
    make_opr(ticket_product, S.paid, donation=1000)
    make_opr(ticket_product, S.used)
    make_opr(ticket_product, S.refunded)

    body = _chart_data(api_client, "bar-ticket-revenue").json()
    row = next(d for d in body["data"] if d["label"] == ticket_product.name)
    assert row["values"]["gross"] == 31000  # 11000 + 10000 + 10000
    assert row["values"]["net"] == 21000  # gross − 10000(refund)


# --- 시계열 (line) ---
def test_sales_trend_buckets(api_client, order_factory):
    order = order_factory(status="completed")
    product_id = str(order.products.get().product_id)
    paid_at = datetime(2026, 8, 15, 10, 0, tzinfo=KST)
    PaymentHistory.objects.filter(order=order).update(created_at=paid_at)

    body = _chart_data(
        api_client,
        "line-sales-trend",
        {"date_range": {"date_from": "2026-08-14", "date_to": "2026-08-16"}, "granularity": "day"},
    ).json()

    assert [d["label"] for d in body["data"]] == ["2026-08-14", "2026-08-15", "2026-08-16"]
    by_label = {d["label"]: d["values"].get(product_id, 0) for d in body["data"]}
    assert by_label == {"2026-08-14": 0, "2026-08-15": 1, "2026-08-16": 0}


def test_sales_trend_missing_date_range_is_400(api_client):
    resp = _chart_data(api_client, "line-sales-trend", {"granularity": "day"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "date_range" in {e["attr"] for e in resp.json()["errors"]}


def test_sales_trend_invalid_granularity_is_400(api_client):
    resp = _chart_data(
        api_client,
        "line-sales-trend",
        {
            "date_range": {"date_from": "2026-08-14", "date_to": "2026-08-16"},
            "granularity": "hour",
        },  # day/week/month 만 허용
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_checkin_trend_uses_history(api_client, make_opr, ticket_product):
    # paid OPR 를 freeze_time 으로 used 전환(save → history 기록).
    opr = make_opr(ticket_product, S.paid)
    with freeze_time("2026-08-15T10:30:00+09:00"):
        opr.status = S.used
        opr.save()

    body = _chart_data(
        api_client,
        "line-checkin-trend",
        {"date_range": {"date_from": "2026-08-15", "date_to": "2026-08-15"}, "granularity": "hour"},
    ).json()

    counts = {d["label"]: d["values"]["checkin"] for d in body["data"]}
    assert counts["2026-08-15 10:00"] == 1
    assert counts["2026-08-15 09:00"] == 0
    assert sum(counts.values()) == 1


def test_checkin_rate_trend_is_cumulative(api_client, make_opr, ticket_product):
    make_opr(ticket_product, S.paid)  # 분모 보강: 전체 판매 2
    opr = make_opr(ticket_product, S.paid)
    with freeze_time("2026-08-15T10:30:00+09:00"):
        opr.status = S.used
        opr.save()

    body = _chart_data(
        api_client,
        "line-checkin-rate-trend",
        {"date_range": {"date_from": "2026-08-15", "date_to": "2026-08-15"}, "granularity": "hour"},
    ).json()

    rate = {d["label"]: d["values"]["rate"] for d in body["data"]}
    assert rate["2026-08-15 09:00"] == 0.0
    assert rate["2026-08-15 10:00"] == 50.0  # 1/2 누적
    assert rate["2026-08-15 23:00"] == 50.0  # 이후 버킷도 누적 유지


# --- 에러 ---
def test_unknown_chart_id_is_404(api_client):
    assert _chart_data(api_client, "nope").status_code == status.HTTP_404_NOT_FOUND


def test_invalid_uuid_param_is_400(api_client):
    resp = _chart_data(api_client, "counter-ticket-paid-total", {"ticket_ids": ["not-a-uuid"]})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert any("ticket_ids" in e["attr"] for e in resp.json()["errors"])


def test_event_filter(api_client, make_opr, ticket_product):
    event = baker.make("event.Event", name="파이콘 한국 2026")
    other_group = CategoryGroup.objects.create(name="기타")
    other_category = Category.objects.create(group=other_group, name="다른 티켓", is_ticket=True, event=event)
    other_product = Product.objects.create(
        category=other_category,
        name="다른 행사 티켓",
        name_ko="다른 행사 티켓",
        name_en="Other Event Ticket",
        price=1000,
        stock=10,
        visible_starts_at=ticket_product.visible_starts_at,
        visible_ends_at=ticket_product.visible_ends_at,
        orderable_starts_at=ticket_product.orderable_starts_at,
        orderable_ends_at=ticket_product.orderable_ends_at,
        refundable_ends_at=ticket_product.refundable_ends_at,
    )
    make_opr(ticket_product, S.paid)  # event 없음
    make_opr(other_product, S.paid)  # event 있음

    resp = _chart_data(api_client, "counter-ticket-paid-total", {"event_id": str(event.id)})
    assert resp.json()["value"] == 1
