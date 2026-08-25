from admin_api.filtersets.shop.products import ProductAdminFilterSet
from admin_api.serializers.shop.products import (
    CategoryGroupAdminSerializer,
    CategoryReadAdminSerializer,
    OptionGroupAdminSerializer,
    ProductAdminSerializer,
    ProductListAdminSerializer,
    TagAdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from django.db.models import Count, Prefetch, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, Tag

READONLY_METHODS = ["list", "retrieve"]
CRUD_METHODS = READONLY_METHODS + ["create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_CATEGORY]) for m in CRUD_METHODS})
class CategoryGroupAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = CategoryGroupAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        CategoryGroup.objects.filter_active()
        .select_related_with_user()
        .prefetch_related(
            Prefetch("category_set", queryset=Category.objects.filter_active().select_related_with_user()),
        )
        .annotate(category_count=Count("category", filter=Q(category__deleted_at__isnull=True)))
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_CATEGORY]) for m in READONLY_METHODS})
class CategoryAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ReadOnlyModelViewSet):
    pagination_class = AdminPagination
    serializer_class = CategoryReadAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_fields = ["group", "event", "is_ticket"]
    queryset = Category.objects.filter_active().select_related_with_user("group", "event")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_TAG]) for m in CRUD_METHODS})
class TagAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = TagAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Tag.objects.filter_active().select_related_with_user().order_by("-created_at", "pk")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_PRODUCT]) for m in CRUD_METHODS})
class ProductAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = ProductAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = ProductAdminFilterSet
    queryset = (
        Product.objects.filter_active()
        .select_related_with_user("category", "category__group", "image")
        .order_by("-created_at", "pk")
    )

    def get_serializer_class(self) -> type:
        return ProductListAdminSerializer if self.action == "list" else ProductAdminSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            # 목록은 판매량만 필요 — 상품별 COUNT 쿼리 대신 annotation 하나로 끝낸다.
            return qs.with_sold_count()

        return qs.prefetch_related(
            # tag_set 은 M2M — serializer 가 읽는 이름 그대로 prefetch 해야 tag_set/tag_set_detail 이 재조회되지 않는다.
            Prefetch("tag_set", queryset=Tag.objects.filter_active().select_related_with_user()),
            Prefetch(
                "option_groups",
                queryset=OptionGroup.objects.filter_active()
                .select_related_with_user()
                .prefetch_related(
                    Prefetch("options", queryset=Option.objects.filter_active().select_related_with_user()),
                ),
            ),
        )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_PRODUCT]) for m in CRUD_METHODS})
class OptionGroupAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = OptionGroupAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        OptionGroup.objects.filter_active()
        .select_related_with_user("product")
        .prefetch_related(Prefetch("options", queryset=Option.objects.filter_active().select_related_with_user()))
    )
