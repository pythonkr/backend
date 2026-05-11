from rest_framework import serializers
from shop.product.models import Option, OptionGroup, Product


class OptionDto(serializers.ModelSerializer):
    class Meta:
        fields = (
            "id",
            "name",
            "additional_price",
            "max_quantity_per_user",
            "leftover_stock",
        )
        model = Option


class OptionGroupDto(serializers.ModelSerializer):
    options = OptionDto(many=True)

    class Meta:
        fields = (
            "id",
            "name",
            "min_quantity_per_product",
            "max_quantity_per_product",
            "is_custom_response",
            "custom_response_pattern",
            "options",
        )
        model = OptionGroup


class ProductDto(serializers.ModelSerializer):
    category_group = serializers.CharField(source="category.group.name")
    category = serializers.CharField(source="category.name")
    option_groups = OptionGroupDto(many=True)
    tag_names: serializers.StringRelatedField = serializers.StringRelatedField(source="tags", many=True)

    class Meta:
        fields = (
            "id",
            "name",
            "description",
            "image",
            "price",
            "donation_allowed",
            "donation_min_price",
            "donation_max_price",
            "orderable_starts_at",
            "orderable_ends_at",
            "refundable_ends_at",
            "category_group",
            "category",
            "option_groups",
            "leftover_stock",
            "tag_names",
        )
        model = Product
