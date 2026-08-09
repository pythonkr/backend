from core.filter.multi_field import MultiFieldOrCharInFilter
from django_filters import rest_framework as filters
from shop.order.models import OrderProductRelation


class OrderProductRelationAdminFilterSet(filters.FilterSet):
    id = filters.BaseInFilter(field_name="id")
    order_id = filters.BaseInFilter(field_name="order_id")
    user_id = filters.BaseInFilter(field_name="order__user_id")
    user_unique_id = filters.BaseInFilter(field_name="order__user__unique_id")
    name = MultiFieldOrCharInFilter(
        field_names=[
            "order__user__nickname_ko",
            "order__user__nickname_en",
            "order__user__username",
            "order__customer_info__name",
            "ticket_info__name",
        ],
        lookup_expr="icontains",
    )
    email = MultiFieldOrCharInFilter(
        field_names=["order__user__email", "order__customer_info__email", "ticket_info__email"],
        lookup_expr="icontains",
    )
    imp_id = MultiFieldOrCharInFilter(field_names=["order_latest_imp_id"], lookup_expr="icontains")

    status = filters.BaseCSVFilter(field_name="status", lookup_expr="in")
    order_status = filters.BaseCSVFilter(field_name="order_current_status", lookup_expr="in")

    first_paid_at_after = filters.DateTimeFilter(field_name="order_first_paid_at", lookup_expr="gte")
    first_paid_at_before = filters.DateTimeFilter(field_name="order_first_paid_at", lookup_expr="lte")

    product_id = filters.BaseInFilter(field_name="product_id")
    category_id = filters.BaseInFilter(field_name="product__category_id")
    category_group_id = filters.BaseInFilter(field_name="product__category__group_id")
    event_id = filters.BaseInFilter(field_name="product__category__event_id")
    is_ticket = filters.BooleanFilter(field_name="product__category__is_ticket")

    price_min = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = OrderProductRelation
        fields = [
            "id",
            "order_id",
            "user_id",
            "user_unique_id",
            "name",
            "email",
            "imp_id",
            "status",
            "order_status",
            "first_paid_at_after",
            "first_paid_at_before",
            "product_id",
            "category_id",
            "category_group_id",
            "event_id",
            "is_ticket",
            "price_min",
            "price_max",
        ]
