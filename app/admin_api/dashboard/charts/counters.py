from admin_api.dashboard.params import CounterParamsSerializer, DashboardParams
from admin_api.dashboard.registry import chart
from django.db.models import Count, Q
from shop.order.models import OrderProductRelation


@chart(
    id="counter-ticket-paid-total",
    title="총 티켓 판매 완료 수",
    type="metric",
    params_serializer=CounterParamsSerializer,
    unit="건",
)
def _paid_total(p: DashboardParams) -> dict:
    return {"value": p.ticket_opr_qs().filter(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS).count()}


@chart(
    id="counter-ticket-refund-total",
    title="총 티켓 환불 수",
    type="metric",
    params_serializer=CounterParamsSerializer,
    unit="건",
)
def _refund_total(p: DashboardParams) -> dict:
    return {"value": p.ticket_opr_qs().filter(status=OrderProductRelation.OrderProductStatus.refunded).count()}


@chart(
    id="counter-checkin-current",
    title="현재 체크인 수",
    type="metric",
    params_serializer=CounterParamsSerializer,
    unit="명",
)
def _checkin_current(p: DashboardParams) -> dict:
    return {"value": p.ticket_opr_qs().filter(status=OrderProductRelation.OrderProductStatus.used).count()}


@chart(
    id="counter-checkin-remaining",
    title="남은 체크인 수",
    type="metric",
    params_serializer=CounterParamsSerializer,
    unit="명",
)
def _checkin_remaining(p: DashboardParams) -> dict:
    return {"value": p.ticket_opr_qs().filter(status=OrderProductRelation.OrderProductStatus.paid).count()}


@chart(
    id="counter-checkin-rate",
    title="체크인율",
    type="metric",
    params_serializer=CounterParamsSerializer,
    unit="%",
)
def _checkin_rate(p: DashboardParams) -> dict:
    agg = p.ticket_opr_qs().aggregate(
        used=Count("id", filter=Q(status=OrderProductRelation.OrderProductStatus.used)),
        total=Count("id", filter=Q(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)),
    )
    return {"value": round(agg["used"] / agg["total"] * 100, 1) if agg["total"] else 0.0}
