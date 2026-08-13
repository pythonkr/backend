from django.db import models
from django_filters import rest_framework as filters
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


class RegistrationDeskOrderProductFilterSet(filters.FilterSet):
    order_product_relation_id = filters.UUIDFilter(field_name="id", lookup_expr="exact")
    scancode = filters.CharFilter(method="filter_by_scancode")

    class Meta:
        model = OrderProductRelation
        fields = ["order_product_relation_id", "scancode"]

    def filter_by_scancode(self, qs: models.QuerySet, name: str, value: str) -> models.QuerySet:
        parts = value.split(":")
        if len(parts) != 3 or parts[0] != OrderProductRelation.scancode_prefix or not all(parts[1:]):
            # 문법 오류는 조회 실패가 아니라 잘못된 요청.
            raise serializers.ValidationError({"scancode": INVALID_SCANCODE_MESSAGE})
        scanned = OrderProductRelation.from_scancode_token(value)
        return qs.filter(pk=scanned.pk) if scanned else qs.none()


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
