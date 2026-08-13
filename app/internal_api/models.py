from __future__ import annotations

import uuid
from datetime import date

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.util.dateutil import now_aware
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.db import models
from shop.product.models import Category


class DateRange(models.Func):
    function = "daterange"
    output_field = DateRangeField()


class RegistrationDeskConfigQuerySet(BaseAbstractModelQuerySet):
    def prefetch_active_targets(self) -> models.QuerySet[RegistrationDeskConfig]:
        return self.prefetch_related(
            models.Prefetch(
                "categories",
                queryset=Category.objects.filter_active().select_related("group"),
            ),
        )

    def filter_by_date(self, on_date: date | None = None) -> models.QuerySet[RegistrationDeskConfig]:
        on_date = on_date or now_aware().date()
        return self.filter(start_date__lte=on_date, end_date__gte=on_date)

    def filter_by_overlap(
        self,
        *,
        start_date: date,
        end_date: date,
        exclude_pk: uuid.UUID | None = None,
    ) -> models.QuerySet[RegistrationDeskConfig]:
        queryset = self.filter(start_date__lte=end_date, end_date__gte=start_date)
        return queryset.exclude(pk=exclude_pk) if exclude_pk else queryset


class RegistrationDeskConfig(BaseAbstractModel):
    """등록 데스크 운영 설정. 날짜만으로 "오늘의 설정" 이 하나로 정해져야 해서 기간 중복을 금지한다."""

    DEFAULT_START_DATE = date(1, 1, 1)
    DEFAULT_END_DATE = date(9999, 12, 31)

    name = models.CharField(max_length=100)
    event = models.ForeignKey("event.Event", on_delete=models.PROTECT, related_name="+")

    start_date = models.DateField(default=DEFAULT_START_DATE)
    end_date = models.DateField(default=DEFAULT_END_DATE)

    categories = models.ManyToManyField("product.Category", related_name="+")

    objects: RegistrationDeskConfigQuerySet = RegistrationDeskConfigQuerySet.as_manager()  # type: ignore

    class Meta:
        ordering = ("start_date", "end_date")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(start_date__lte=models.F("end_date")),
                name="registration_desk_config_period_order",
            ),
            ExclusionConstraint(
                name="registration_desk_config_period_overlap",
                expressions=[
                    (DateRange("start_date", "end_date", RangeBoundary(inclusive_upper=True)), RangeOperators.OVERLAPS),
                ],
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def build_query(self) -> models.Q:
        category_ids = list(self.categories.filter_active().values_list("id", flat=True))
        return models.Q(product__category_id__in=category_ids)

    def covers(self, order_product_relation_ids: list[uuid.UUID]) -> bool:
        from shop.order.models import OrderProductRelation

        covered = (
            OrderProductRelation.objects.filter_active()
            .filter(self.build_query())
            .filter(id__in=order_product_relation_ids)
            .count()
        )
        return covered == len(set(order_product_relation_ids))
