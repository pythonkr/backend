from django.db import models
from django_filters import rest_framework as filters
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, OrderQuerySet
from user.models import UserExt


class DeskSupportFilterSet(filters.FilterSet):
    category_groups = filters.BaseCSVFilter(method="filter_by_category_groups")
    categories = filters.BaseCSVFilter(method="filter_by_categories")
    keywords = filters.BaseCSVFilter(method="filter_by_keywords")

    user_unique_id = filters.UUIDFilter(field_name="user__unique_id", lookup_expr="exact")
    order_product_relation_id = filters.UUIDFilter(method="filter_by_order_product_relation_id")
    order_id = filters.UUIDFilter(field_name="id", lookup_expr="exact")

    class Meta:
        model = Order
        fields = [
            "category_groups",
            "categories",
            "keywords",
            "user_unique_id",
            "order_product_relation_id",
            "order_id",
        ]

    def filter_by_category_groups(self, qs: OrderQuerySet, name: str, values: list[str]) -> OrderQuerySet:
        if not (filtered_values := [v.strip() for v in values if v.strip()]):
            return qs

        opor_order_qs = OrderProductRelation.objects.filter(
            product__category__group__name__in=filtered_values,
        ).values_list("order_id", flat=True)

        return qs.filter(id__in=opor_order_qs)

    def filter_by_categories(self, qs: OrderQuerySet, name: str, values: list[str]) -> OrderQuerySet:
        if not (filtered_values := [v.strip() for v in values if v.strip()]):
            return qs

        opor_order_qs = OrderProductRelation.objects.filter(
            product__category__name__in=filtered_values,
        ).values_list("order_id", flat=True)

        return qs.filter(id__in=opor_order_qs)

    def filter_by_order_product_relation_id(self, qs: OrderQuerySet, name: str, value: str) -> OrderQuerySet:
        if not value:
            return qs

        return qs.filter(id__in=OrderProductRelation.objects.filter(id=value).values_list("order_id", flat=True))

    def filter_by_keywords(self, qs: OrderQuerySet, name: str, values: list[str]) -> OrderQuerySet:
        if not (filtered_values := [v.strip() for v in values if v.strip()]):
            return qs

        opor_order_qs = OrderProductOptionRelation.objects.filter(
            custom_response__in=filtered_values,
        ).values_list("order_product_relation__order_id", flat=True)
        ci_order_qs = CustomerInfo.objects.filter(
            models.Q(name__in=filtered_values)
            | models.Q(email__in=filtered_values)
            | models.Q(phone__in=filtered_values)
            | models.Q(organization__in=filtered_values)
        ).values_list("order_id", flat=True)

        user_subquery = models.Q()
        for value in filtered_values:
            user_subquery |= models.Q(username__icontains=value) | models.Q(email__icontains=value)
        user_order_qs = qs.filter(user__in=UserExt.objects.filter(user_subquery)).values_list("id", flat=True)

        return qs.filter(models.Q(id__in=opor_order_qs) | models.Q(id__in=ci_order_qs) | models.Q(id__in=user_order_qs))
