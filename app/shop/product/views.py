from collections.abc import Iterable
from typing import Any

from core.const.tag import OpenAPITag
from django.db.models import Prefetch, Q, QuerySet
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import ErrorResponse404Serializer
from rest_framework import mixins, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from shop.order.models import OrderProductOptionRelation, OrderProductRelation
from shop.product.filtersets import ProductFilterSet
from shop.product.models import Option, OptionGroup, Product, ProductTagRelation
from shop.product.serializers.dto import ProductDto, StockContext
from user.models import UserExt


def build_stock_context(products: Iterable[Product], user: UserExt | None) -> StockContext:
    """직렬화할 product 집합으로 scope 한 OPR 1쿼리 + OPOR 1쿼리만으로 StockContext 5 Counter 를 채운다.

    status filter 는 글로벌 잔여재고(PURCHASED) ∪ 유저 점유(pending + purchased) — 익명이면 후자 절을 빼서 한 쿼리에 묶는다.
    product_option_id 는 custom_response 행에서 NULL 이라 글로벌 option 카운트에서 제외.
    """
    if not (product_ids := [p.id for p in products]):
        return StockContext()

    user_id = user and user.id

    status_q = Q(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)
    if user:
        status_q |= Q(status=OrderProductRelation.OrderProductStatus.pending, order__user=user)
    opr_rows = (
        OrderProductRelation.objects.filter_active()
        .filter(status_q, product_id__in=product_ids, single_product_cart__isnull=True)
        .values_list("product_id", "status", "order__user_id")
    )
    ctx = StockContext(covered_product_ids=frozenset(product_ids))
    for product_id, opr_status, opr_user_id in opr_rows:
        if opr_status in OrderProductRelation.PURCHASED_STOCK_STATUS:
            ctx.global_product_purchased[product_id] += 1
        if opr_user_id == user_id:
            ctx.user_product_taken[product_id] += 1

    opor_status_q = Q(order_product_relation__status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)
    if user:
        opor_status_q |= Q(
            order_product_relation__status=OrderProductRelation.OrderProductStatus.pending,
            order_product_relation__order__user=user,
        )
    opor_rows = (
        OrderProductOptionRelation.objects.filter_active()
        .filter(
            opor_status_q,
            order_product_relation__product_id__in=product_ids,
            order_product_relation__single_product_cart__isnull=True,
            order_product_relation__deleted_at__isnull=True,
        )
        .values_list(
            "product_option_id",
            "product_option_group_id",
            "order_product_relation__status",
            "order_product_relation__order__user_id",
        )
    )
    for option_id, group_id, opor_status, opor_user_id in opor_rows:
        if opor_status in OrderProductRelation.PURCHASED_STOCK_STATUS and option_id is not None:
            ctx.global_option_purchased[option_id] += 1
        if opor_user_id == user_id:
            ctx.user_group_taken[group_id] += 1
            if option_id is not None:
                ctx.user_option_taken[option_id] += 1

    return ctx


@extend_schema_view(
    list=extend_schema(
        summary="상품 목록 조회",
        tags=[OpenAPITag.SHOP_PRODUCT],
        responses={status.HTTP_200_OK: ProductDto(many=True)},
    ),
    retrieve=extend_schema(
        summary="상품 상세 조회",
        tags=[OpenAPITag.SHOP_PRODUCT],
        parameters=[
            OpenApiParameter(
                name="product_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            status.HTTP_200_OK: ProductDto,
            status.HTTP_404_NOT_FOUND: ErrorResponse404Serializer,
        },
    ),
)
class ProductViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_url_kwarg = "product_id"
    authentication_classes = []
    permission_classes = []
    serializer_class = ProductDto
    filterset_class = ProductFilterSet

    def get_queryset(self) -> QuerySet[Product]:
        base_qs = Product.objects.filter_visible_now()

        if self.action == "retrieve" and isinstance(self.request.user, UserExt):
            # 단, 사용자가 구매한 상품인 경우, 노출 기간에 상관없이 상세 정보를 조회할 수 있어야 합니다.
            purchased_product_ids = (
                OrderProductRelation.objects.filter_active()
                .filter(
                    order__user=self.request.user,
                    single_product_cart__isnull=True,
                    status=OrderProductRelation.OrderProductStatus.paid,
                )
                .values_list("product_id", flat=True)
            )
            base_qs = base_qs | Product.objects.filter_active().filter(id__in=purchased_product_ids)

        return base_qs.select_related("category", "category__group", "image").prefetch_related(
            Prefetch("tags", queryset=ProductTagRelation.objects.filter_active().select_related("tag")),
            Prefetch(
                "option_groups",
                queryset=OptionGroup.objects.filter_visible_now()
                .select_related("product")
                .prefetch_related(
                    Prefetch("options", queryset=Option.objects.filter_active().select_related("group__product"))
                ),
            ),
        )

    def get_serializer_context(self) -> dict[str, Any]:
        return super().get_serializer_context() | (
            {"stock_context": sc} if (sc := getattr(self, "_stock_context", None)) else {}
        )

    @property
    def user(self) -> UserExt | None:
        return self.request.user if isinstance(self.request.user, UserExt) else None

    def list(self, request: Request, *_args: Any, **_kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        instances: list[Product] = list(page) if page is not None else list(queryset)
        self._stock_context = build_stock_context(products=instances, user=self.user)
        serializer = self.get_serializer(instances, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def retrieve(self, request: Request, *_args: Any, **_kwargs: Any) -> Response:
        instance = self.get_object()
        self._stock_context = build_stock_context(products=[instance], user=self.user)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
