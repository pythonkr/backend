from admin_api.serializers.shop.products import (
    CategoryGroupAdminSerializer,
    OptionGroupAdminSerializer,
    ProductAdminSerializer,
    TagAdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, ProductTagRelation, Tag

READONLY_METHODS = ["list", "retrieve"]
CRUD_METHODS = READONLY_METHODS + ["create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_CATEGORY]) for m in CRUD_METHODS})
class CategoryGroupAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = CategoryGroupAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        CategoryGroup.objects.filter_active()
        .select_related_with_user()
        .prefetch_related(
            Prefetch("category_set", queryset=Category.objects.filter_active().select_related_with_user()),
        )
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_TAG]) for m in CRUD_METHODS})
class TagAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = TagAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Tag.objects.filter_active().select_related_with_user()


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_PRODUCT]) for m in CRUD_METHODS})
class ProductAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = ProductAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        Product.objects.filter_active()
        .select_related_with_user("category", "category__group")
        .prefetch_related(
            Prefetch("tags", queryset=ProductTagRelation.objects.filter_active().select_related("tag")),
            Prefetch(
                "option_groups",
                queryset=OptionGroup.objects.filter_active()
                .select_related_with_user()
                .prefetch_related(
                    Prefetch("options", queryset=Option.objects.filter_active().select_related_with_user()),
                ),
            ),
        )
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_PRODUCT]) for m in CRUD_METHODS})
class OptionGroupAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = OptionGroupAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        OptionGroup.objects.filter_active()
        .select_related_with_user("product")
        .prefetch_related(Prefetch("options", queryset=Option.objects.filter_active().select_related_with_user()))
    )
