import operator
from functools import reduce

from django.core.validators import EMPTY_VALUES
from django.db.models import Q
from django_filters import rest_framework as filters


class MultiFieldOrFilterMixin:
    """`field_names` 의 여러 필드에 같은 lookup 을 OR 로 적용.

    BaseCSVFilter 와 함께 상속하면 CSV 입력 (`"a,b,c"` → `["a", "b", "c"]`) 도 자동 처리되어,
    각 값마다 모든 필드에 lookup → 전체 OR 매칭.
    """

    def __init__(self, *args: tuple, field_names: list[str] | None = None, **kwargs: dict) -> None:
        self.field_names: list[str] = field_names or []
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):  # type: ignore[no-untyped-def]
        if value in EMPTY_VALUES:
            return qs
        if not self.field_names:
            return super().filter(qs, value)
        if self.distinct:
            qs = qs.distinct()

        # CSV 입력은 list, 단일 입력은 scalar
        values = value if isinstance(value, list) else [value]
        conditions = [
            Q(**{f"{field}__{self.lookup_expr}": v})
            for v in values
            if v not in EMPTY_VALUES
            for field in self.field_names
        ]
        return qs.filter(reduce(operator.or_, conditions)) if conditions else qs


class MultiFieldOrCharFilter(MultiFieldOrFilterMixin, filters.CharFilter):
    """단일 value, multi-field OR."""


class MultiFieldOrCharInFilter(MultiFieldOrFilterMixin, filters.BaseCSVFilter, filters.CharFilter):
    """CSV value (콤마 구분 list), multi-field OR. `lookup_expr` (예: `icontains`) 로 부분 매칭."""
