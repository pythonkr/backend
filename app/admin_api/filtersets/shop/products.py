from core.filter.multi_field import MultiFieldOrCharInFilter
from core.util.dateutil import now_aware
from django.db.models import Q
from django_filters import rest_framework as filters
from shop.product.models import Product


class ProductAdminFilterSet(filters.FilterSet):
    id = filters.BaseInFilter(field_name="id")
    name = MultiFieldOrCharInFilter(field_names=["name_ko", "name_en"], lookup_expr="icontains")
    category = filters.BaseInFilter(field_name="category_id")
    category_group = filters.BaseInFilter(field_name="category__group_id")
    tag = filters.BaseInFilter(field_name="tag_set", distinct=True)

    price_min = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="price", lookup_expr="lte")

    status = filters.BaseCSVFilter(method="filter_by_status")

    def filter_by_status(self, queryset, name, values):
        now = now_aware()
        q = Q()
        for value in values:
            if value == Product.CurrentStatus.OUT_OF_VISIBLE_PERIOD:
                q |= Q(visible_starts_at__gt=now) | Q(visible_ends_at__lt=now)
            elif value == Product.CurrentStatus.OUT_OF_ORDERABLE_PERIOD:
                q |= (
                    Q(visible_starts_at__lte=now)
                    & Q(visible_ends_at__gte=now)
                    & (Q(orderable_starts_at__gt=now) | Q(orderable_ends_at__lt=now))
                )
            elif value == Product.CurrentStatus.ACTIVE:
                q |= (
                    Q(visible_starts_at__lte=now)
                    & Q(visible_ends_at__gte=now)
                    & Q(orderable_starts_at__lte=now)
                    & Q(orderable_ends_at__gte=now)
                )
        return queryset.filter(q).distinct()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_group",
            "tag",
            "price_min",
            "price_max",
            "status",
        ]
