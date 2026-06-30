from core.filter.multi_field import MultiFieldOrCharInFilter
from django.db.models import Exists, OuterRef, QuerySet
from django_filters import rest_framework as filters
from shop.order.models import Order, OrderProductRelation


class OrderAdminFilterSet(filters.FilterSet):
    """admin 운영자 검색. CSV (콤마 구분) 다중 값 지원: `?name=철수,영희&status=completed,refunded`"""

    id = filters.BaseInFilter(field_name="id")
    user_id = filters.BaseInFilter(field_name="user_id")
    user_unique_id = filters.BaseInFilter(field_name="user__unique_id")
    name = MultiFieldOrCharInFilter(
        field_names=["user__nickname_ko", "user__nickname_en", "user__username", "customer_info__name"],
        lookup_expr="icontains",
    )
    email = MultiFieldOrCharInFilter(field_names=["user__email", "customer_info__email"], lookup_expr="icontains")
    imp_id = MultiFieldOrCharInFilter(field_names=["latest_imp_id"], lookup_expr="icontains")
    status = filters.BaseCSVFilter(field_name="current_status", lookup_expr="in")

    created_at_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    first_paid_at_after = filters.DateTimeFilter(field_name="first_paid_at", lookup_expr="gte")
    first_paid_at_before = filters.DateTimeFilter(field_name="first_paid_at", lookup_expr="lte")

    status_changed_at_after = filters.DateTimeFilter(field_name="status_changed_at", lookup_expr="gte")
    status_changed_at_before = filters.DateTimeFilter(field_name="status_changed_at", lookup_expr="lte")

    product_id = filters.BaseCSVFilter(method="filter_by_active_opr_product_id")
    category_id = filters.BaseCSVFilter(method="filter_by_active_opr_category_id")
    category_group_id = filters.BaseCSVFilter(method="filter_by_active_opr_category_group_id")
    event_id = filters.BaseCSVFilter(method="filter_by_active_opr_event_id")

    price_min = filters.NumberFilter(field_name="latest_price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="latest_price", lookup_expr="lte")

    def _filter_by_active_opr_exists(self, qs: QuerySet[Order], **kw: object) -> QuerySet[Order]:
        return qs.filter(Exists(OrderProductRelation.objects.filter_active().filter(order_id=OuterRef("pk"), **kw)))

    def filter_by_active_opr_product_id(self, qs: QuerySet[Order], n: str, vs: list[str]) -> QuerySet[Order]:
        return self._filter_by_active_opr_exists(qs, product_id__in=vs) if vs else qs

    def filter_by_active_opr_category_id(self, qs: QuerySet[Order], n: str, vs: list[str]) -> QuerySet[Order]:
        return self._filter_by_active_opr_exists(qs, product__category_id__in=vs) if vs else qs

    def filter_by_active_opr_category_group_id(self, qs: QuerySet[Order], n: str, v: list[str]) -> QuerySet[Order]:
        return self._filter_by_active_opr_exists(qs, product__category__group_id__in=v) if v else qs

    def filter_by_active_opr_event_id(self, qs: QuerySet[Order], n: str, vs: list[str]) -> QuerySet[Order]:
        return self._filter_by_active_opr_exists(qs, product__category__event_id__in=vs) if vs else qs

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "user_unique_id",
            "name",
            "email",
            "imp_id",
            "status",
            "created_at_after",
            "created_at_before",
            "first_paid_at_after",
            "first_paid_at_before",
            "status_changed_at_after",
            "status_changed_at_before",
            "product_id",
            "category_id",
            "category_group_id",
            "event_id",
            "price_min",
            "price_max",
        ]
