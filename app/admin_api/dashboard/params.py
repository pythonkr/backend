from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from core.const.datetime import Granularity
from core.serializer.date_range_serializer import DateRangeSerializer
from django.db.models import QuerySet
from rest_framework import serializers
from shop.order.models import OrderProductRelation

REVENUE_GROSS, REVENUE_NET = "gross", "net"


# --- 동적 옵션 마커 필드 (옵션은 정의 빌드 시 DB 에서 주입) ---
class _TicketIdsField(serializers.ListField):
    dynamic_options = "tickets"  # 정의 introspection 이 읽는 마커

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("child", serializers.UUIDField())  # Product.id (UUID)
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", "티켓")
        super().__init__(**kwargs)


class _EventIdField(serializers.UUIDField):
    param_type = "select"
    dynamic_options = "events"

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("label", "이벤트")
        super().__init__(**kwargs)


# --- shape 별 params serializer (검증 + 정의 역생성의 단일 소스) ---
class CounterParamsSerializer(serializers.Serializer):
    event_id = _EventIdField()
    ticket_ids = _TicketIdsField()


class _TimeSeriesParamsSerializer(CounterParamsSerializer):
    date_range = DateRangeSerializer(required=True, label="조회 기간")


class SalesTrendParamsSerializer(_TimeSeriesParamsSerializer):
    granularity = serializers.ChoiceField(
        choices=[(g.value, g.label) for g in (Granularity.DAY, Granularity.WEEK, Granularity.MONTH)],
        default=Granularity.DAY.value,
        label="집계 단위",
    )


class RevenueTrendParamsSerializer(SalesTrendParamsSerializer):
    revenue_type = serializers.ChoiceField(
        choices=[(REVENUE_GROSS, "총매출"), (REVENUE_NET, "순매출")],
        default=REVENUE_GROSS,
        label="매출 종류",
    )


class CheckinTrendParamsSerializer(_TimeSeriesParamsSerializer):
    granularity = serializers.ChoiceField(
        choices=[(g.value, g.label) for g in (Granularity.HOUR, Granularity.DAY)],
        default=Granularity.HOUR.value,
        label="집계 단위",
    )


@dataclass(frozen=True)
class DashboardParams:
    date_from: datetime | None = None
    date_to: datetime | None = None
    granularity: str | None = None
    event_id: UUID | None = None
    ticket_ids: tuple[UUID, ...] = ()
    revenue_type: str = REVENUE_GROSS

    @classmethod
    def from_validated(cls, data: dict) -> DashboardParams:
        date_range = data.get("date_range") or {}
        return cls(
            date_from=date_range.get("date_from"),
            date_to=date_range.get("date_to"),
            granularity=data.get("granularity"),
            event_id=data.get("event_id") or None,
            ticket_ids=tuple(data.get("ticket_ids") or ()),
            revenue_type=data.get("revenue_type") or REVENUE_GROSS,
        )

    def ticket_opr_qs(self) -> QuerySet[OrderProductRelation]:
        qs = OrderProductRelation.objects.filter_active().filter(product__category__is_ticket=True)
        if self.event_id:
            qs = qs.filter(product__category__event_id=self.event_id)
        if self.ticket_ids:
            qs = qs.filter(product_id__in=self.ticket_ids)
        return qs
