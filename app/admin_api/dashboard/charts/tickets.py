from admin_api.dashboard.params import CounterParamsSerializer, DashboardParams
from admin_api.dashboard.registry import chart
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from shop.order.models import OrderProductRelation

# 매출 금액 = 상품가 + 후원금.
AMOUNT = F("price") + F("donation_price")


@chart(
    id="bar-ticket-paid-count",
    title="티켓별 판매 수",
    type="bar",
    params_serializer=CounterParamsSerializer,
    unit="건",
)
def _paid_count(p: DashboardParams) -> dict:
    rows = (
        p.ticket_opr_qs()
        .filter(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)
        .values("product_id", "product__name")
        .annotate(n=Count("id"))
        .order_by("product__name")
    )
    return {
        "series": [{"key": "count", "name": "판매 수"}],
        "data": [{"label": r["product__name"], "values": {"count": r["n"]}} for r in rows],
    }


@chart(
    id="bar-ticket-revenue",
    title="티켓별 매출액",
    type="bar",
    params_serializer=CounterParamsSerializer,
    unit="원",
    options={"value_format": ",.0f"},
)
def _revenue(p: DashboardParams) -> dict:
    rows = (
        p.ticket_opr_qs()
        .filter(status__in=OrderProductRelation.PURCHASED_OR_REFUNDED_STATUS)
        .values("product_id", "product__name")
        .annotate(
            gross=Coalesce(Sum(AMOUNT), 0),
            refund=Coalesce(Sum(AMOUNT, filter=Q(status=OrderProductRelation.OrderProductStatus.refunded)), 0),
        )
        .annotate(net=F("gross") - F("refund"))  # 순매출 = 총매출 − 환불액
        .order_by("product__name")
    )
    return {
        "series": [{"key": "gross", "name": "총매출"}, {"key": "net", "name": "순매출"}],
        "data": [{"label": r["product__name"], "values": {"gross": r["gross"], "net": r["net"]}} for r in rows],
    }
