from datetime import date

from core.util.dateutil import now_aware
from django.db import models
from django.db.models.functions import Lower, Trim
from django_filters import rest_framework as filters
from internal_api.models import RegistrationDeskConfig
from rest_framework import serializers
from shop.order.models import (
    CustomerInfo,
    Order,
    OrderProductOptionRelation,
    OrderProductRelation,
    OrderQuerySet,
    TicketInfo,
)
from user.models import UserExt

INVALID_SCANCODE_MESSAGE = "스캔코드 형식이 올바르지 않습니다."

# 2026 프로그램 등록일에만 쓰는 임시 묶음 조회다. 행사 종료 뒤 제거한다.
TEMPORARY_RELATED_TICKET_DATE = date(2026, 8, 17)
TEMPORARY_RELATED_TICKET_CATEGORIES = frozenset({"스프린트", "튜토리얼", "딥다이브"})


class RegistrationDeskOrderProductFilterSet(filters.FilterSet):
    order_product_relation_id = filters.UUIDFilter(field_name="id", lookup_expr="exact")
    scancode = filters.CharFilter(method="filter_by_scancode")
    include_related_ticketinfo = filters.BooleanFilter(method="filter_related_ticketinfo")

    class Meta:
        model = OrderProductRelation
        fields = ["order_product_relation_id", "scancode", "include_related_ticketinfo"]

    def filter_by_scancode(self, qs: models.QuerySet, name: str, value: str) -> models.QuerySet:
        parts = value.split(":")
        if len(parts) != 3 or parts[0] != OrderProductRelation.scancode_prefix or not all(parts[1:]):
            # 문법 오류는 조회 실패가 아니라 잘못된 요청.
            raise serializers.ValidationError({"scancode": INVALID_SCANCODE_MESSAGE})
        scanned = OrderProductRelation.from_scancode_token(value)
        return qs.filter(pk=scanned.pk) if scanned else qs.none()

    def filter_related_ticketinfo(self, qs: models.QuerySet, name: str, value: bool) -> models.QuerySet:
        """오늘 프로그램 티켓 QR 하나로 같은 참가자의 오늘 티켓을 함께 조회한다.

        명시적인 opt-in 파라미터와 날짜/카테고리 가드를 모두 만족해야 확장한다.
        일반 주문상품 조회, 다른 행사일 및 대상 밖 QR은 기존 단건 동작을 유지한다.
        """
        if not value or not self.data.get("scancode") or now_aware().date() != TEMPORARY_RELATED_TICKET_DATE:
            return qs

        scanned = qs.select_related("product__category", "ticket_info").first()
        if not scanned or not (ticket_info := scanned.ticket_info_or_none):
            return qs

        config = RegistrationDeskConfig.objects.filter_active().filter_by_date(TEMPORARY_RELATED_TICKET_DATE).first()
        if (
            not config
            or not config.categories.filter(
                id=scanned.product.category_id,
                name__in=TEMPORARY_RELATED_TICKET_CATEGORIES,
                deleted_at__isnull=True,
            ).exists()
        ):
            return qs

        normalized_email = ticket_info.email.strip().lower()
        if not normalized_email:
            return qs

        return (
            self.queryset.filter(
                config.build_query(),
                status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
                product__category__name__in=TEMPORARY_RELATED_TICKET_CATEGORIES,
                ticket_info__deleted_at__isnull=True,
            )
            .annotate(_normalized_ticket_email=Lower(Trim("ticket_info__email")))
            .filter(_normalized_ticket_email=normalized_email)
        )


class RegistrationDeskOrderFilterSet(filters.FilterSet):
    keywords = filters.BaseCSVFilter(method="filter_by_keywords")

    user_unique_id = filters.UUIDFilter(field_name="user__unique_id", lookup_expr="exact")
    order_product_relation_id = filters.UUIDFilter(method="filter_by_order_product_relation_id")
    order_id = filters.UUIDFilter(field_name="id", lookup_expr="exact")

    class Meta:
        model = Order
        fields = [
            "keywords",
            "user_unique_id",
            "order_product_relation_id",
            "order_id",
        ]

    def filter_by_order_product_relation_id(self, qs: OrderQuerySet, name: str, value: str) -> OrderQuerySet:
        if not value:
            return qs

        return qs.filter(
            id__in=OrderProductRelation.objects.filter_active().filter(id=value).values_list("order_id", flat=True)
        )

    def filter_by_keywords(self, qs: OrderQuerySet, name: str, values: list[str]) -> OrderQuerySet:
        if not (filtered_values := [v.strip() for v in values if v.strip()]):
            return qs

        participant_query = (
            models.Q(name__in=filtered_values)
            | models.Q(email__in=filtered_values)
            | models.Q(phone__in=filtered_values)
            | models.Q(organization__in=filtered_values)
        )

        opor_order_qs = (
            OrderProductOptionRelation.objects.filter_active()
            .filter(custom_response__in=filtered_values)
            .values_list("order_product_relation__order_id", flat=True)
        )
        ci_order_qs = CustomerInfo.objects.filter(participant_query).values_list("order_id", flat=True)
        ti_order_qs = (
            TicketInfo.objects.filter_active()
            .filter(participant_query, order_product_relation__deleted_at__isnull=True)
            .values_list("order_product_relation__order_id", flat=True)
        )

        user_query = models.Q()
        for value in filtered_values:
            user_query |= models.Q(username__icontains=value) | models.Q(email__icontains=value)

        return qs.filter(
            models.Q(id__in=opor_order_qs)
            | models.Q(id__in=ci_order_qs)
            | models.Q(id__in=ti_order_qs)
            | models.Q(user__in=UserExt.objects.filter(user_query))
        )
