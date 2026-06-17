from __future__ import annotations

from collections import defaultdict

from admin_api.dashboard.params import (
    REVENUE_NET,
    CheckinTrendParamsSerializer,
    DashboardParams,
    RevenueTrendParamsSerializer,
    SalesTrendParamsSerializer,
)
from admin_api.dashboard.registry import chart
from core.util.dateutil import period_label, period_label_range
from django.db.models import Min, OuterRef, Subquery
from shop.order.models import OrderProductRelation
from shop.payment_history.models import PaymentHistory


def first_paid_at_subquery() -> Subquery:
    """OPR 의 주문에 대한 첫 PaymentHistory.created_at (판매 시각). OPR 컨텍스트용(OuterRef order_id)."""
    return Subquery(
        PaymentHistory.objects.filter_active()
        .filter(order_id=OuterRef("order_id"))
        .order_by("created_at")
        .values("created_at")[:1]
    )


def assemble_product_series(agg: dict[tuple[str, object], object], names: dict[object, str], p) -> dict:
    """{(label, product_id): value} + {product_id: name} → series + 연속 data(빈 버킷 0)."""
    series = [{"key": str(pid), "name": name} for pid, name in names.items()]
    data = []
    for label in period_label_range(p.date_from, p.date_to, p.granularity):
        values = {str(pid): agg.get((label, pid), 0) for pid in names}
        data.append({"label": label, "values": values})
    return {"series": series, "data": data}


def checkin_counts_by_label(p) -> dict[str, int]:
    """현재 used 인 티켓 OPR 의 '최초 used 전이' 시각(history)을 주기별로 집계. {label: count}."""
    historical = OrderProductRelation.history.model
    target_ids = (
        p.ticket_opr_qs().filter(status=OrderProductRelation.OrderProductStatus.used).values_list("id", flat=True)
    )
    rows = (
        historical.objects.filter(id__in=target_ids, status=OrderProductRelation.OrderProductStatus.used)
        .values("id")
        .annotate(checked_at=Min("history_date"))
        .filter(checked_at__gte=p.date_from, checked_at__lt=p.date_to)
    )
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[period_label(row["checked_at"], p.granularity)] += 1
    return counts


@chart(
    id="line-sales-trend",
    title="판매 추이",
    type="line",
    params_serializer=SalesTrendParamsSerializer,
    unit="건",
)
def _sales_trend(p: DashboardParams) -> dict:
    rows = (
        p.ticket_opr_qs()
        .filter(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)
        .annotate(paid_at=first_paid_at_subquery())
        .filter(paid_at__gte=p.date_from, paid_at__lt=p.date_to)
        .values_list("product_id", "product__name", "paid_at")
    )
    agg: dict[tuple[str, object], int] = defaultdict(int)
    names: dict[object, str] = {}
    for pid, name, paid_at in rows:
        names.setdefault(pid, name)
        agg[(period_label(paid_at, p.granularity), pid)] += 1
    return assemble_product_series(agg, names, p)


@chart(
    id="line-revenue-trend",
    title="매출 추이",
    type="line",
    params_serializer=RevenueTrendParamsSerializer,
    unit="원",
    options={"value_format": ",.0f"},
)
def _revenue_trend(p: DashboardParams) -> dict:
    # 순매출 = 환불 제외(paid+used). 총매출 = 환불 포함 결제총액. (판매 시각 기준 — 환불 시점은 미반영)
    statuses = (
        OrderProductRelation.PURCHASED_STOCK_STATUS
        if p.revenue_type == REVENUE_NET
        else OrderProductRelation.PURCHASED_OR_REFUNDED_STATUS
    )
    rows = (
        p.ticket_opr_qs()
        .filter(status__in=statuses)
        .annotate(paid_at=first_paid_at_subquery())
        .filter(paid_at__gte=p.date_from, paid_at__lt=p.date_to)
        .values_list("product_id", "product__name", "price", "donation_price", "paid_at")
    )
    agg: dict[tuple[str, object], int] = defaultdict(int)
    names: dict[object, str] = {}
    for pid, name, price, donation, paid_at in rows:
        names.setdefault(pid, name)
        agg[(period_label(paid_at, p.granularity), pid)] += price + donation
    return assemble_product_series(agg, names, p)


@chart(
    id="line-checkin-trend", title="체크인 추이", type="line", params_serializer=CheckinTrendParamsSerializer, unit="명"
)
def _checkin_trend(p: DashboardParams) -> dict:
    counts = checkin_counts_by_label(p)
    data = [
        {"label": label, "values": {"checkin": counts.get(label, 0)}}
        for label in period_label_range(p.date_from, p.date_to, p.granularity)
    ]
    return {"series": [{"key": "checkin", "name": "체크인 수"}], "data": data}


@chart(
    id="line-checkin-rate-trend",
    title="체크인율 추이",
    type="line",
    params_serializer=CheckinTrendParamsSerializer,
    unit="%",
)
def _checkin_rate_trend(p: DashboardParams) -> dict:
    counts = checkin_counts_by_label(p)
    total = p.ticket_opr_qs().filter(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS).count()
    data = []
    cumulative = 0
    for label in period_label_range(p.date_from, p.date_to, p.granularity):
        cumulative += counts.get(label, 0)
        pct = round(cumulative / total * 100, 1) if total else 0.0
        data.append({"label": label, "values": {"rate": pct}})
    return {"series": [{"key": "rate", "name": "체크인율"}], "data": data}
