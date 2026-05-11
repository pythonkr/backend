from django_filters import rest_framework as filters
from shop.product.models import Product


class ProductFilterSet(filters.FilterSet):
    category_group = filters.CharFilter(field_name="category__group__name", lookup_expr="exact")
    category = filters.CharFilter(field_name="category__name", lookup_expr="exact")

    class Meta:
        model = Product
        fields = ["category_group", "category"]
