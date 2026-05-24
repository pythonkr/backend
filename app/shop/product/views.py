from core.const.tag import OpenAPITag
from django.db.models import Prefetch, QuerySet
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import ErrorResponse404Serializer
from rest_framework import mixins, status, viewsets
from shop.order.models import OrderProductRelation
from shop.product.filtersets import ProductFilterSet
from shop.product.models import OptionGroup, Product
from shop.product.serializers.dto import ProductDto
from user.models import UserExt


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
            purchased_product_ids = OrderProductRelation.objects.filter(
                order__user=self.request.user,
                single_product_cart__isnull=True,
                status=OrderProductRelation.OrderProductStatus.paid,
            ).values_list("product_id", flat=True)
            base_qs = base_qs | Product.objects.filter_active().filter(id__in=purchased_product_ids)

        return base_qs.select_related("category", "category__group", "image").prefetch_related(
            "tags",
            Prefetch(
                "option_groups",
                queryset=OptionGroup.objects.filter_visible_now().prefetch_related("options"),
            ),
        )
