from core.filter.multi_field import MultiFieldOrCharInFilter
from django_filters import rest_framework as filters
from shop.order.models import Order


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

    price_min = filters.NumberFilter(field_name="latest_price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="latest_price", lookup_expr="lte")

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
            "price_min",
            "price_max",
        ]
