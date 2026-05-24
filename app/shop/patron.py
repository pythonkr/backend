from core.const.tag import OpenAPITag
from django.db.models import CharField, DecimalField, Exists, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, routers, serializers, status, viewsets
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import REFUNDABLE_STATUSES, PaymentHistory


class PatronFilterSet(filters.FilterSet):
    year = filters.NumberFilter(field_name="created_at__year")

    class Meta:
        model = Order
        fields = ["year"]


class PatronSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="customer_info.name", allow_null=True)

    class Meta:
        fields: list[str] = ["name"]
        model = Order

    def to_representation(self, instance: Order) -> dict[str, str]:
        result = super().to_representation(instance)

        opor: OrderProductOptionRelation = (
            OrderProductOptionRelation.objects.filter_active()
            .filter(
                Q(product_option_group__name__contains="후원자") | Q(product_option_group__name__contains="message"),
                order_product_relation__order=instance,
                order_product_relation__deleted_at__isnull=True,
                product_option_group__name__contains="후원자",
                product_option_group__is_custom_response=True,
            )
            .first()
        )
        return result | {"contribution_message": opor.custom_response if opor else ""}


@extend_schema_view(
    list=extend_schema(
        summary="개인 후원자 목록",
        tags=[OpenAPITag.EXT_PATRON_API],
        responses={status.HTTP_200_OK: PatronSerializer(many=True)},
    ),
)
class PatronViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    latest_status_sq = (
        PaymentHistory.objects.filter_active()
        .filter(order_id=OuterRef("id"))
        .order_by("-created_at")
        .values("status")[:1]
    )
    total_paid_sq = (
        OrderProductRelation.objects.filter_active()
        .filter(
            order_id=OuterRef("id"),
            status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
        )
        .values("order_id")
        .annotate(total=Sum(F("price") + F("donation_price")))
        .values("total")
    )

    queryset = (
        Order.objects.filter_active()
        .annotate(
            current_status=Subquery(latest_status_sq, output_field=CharField()),
            has_donation_product=Exists(
                OrderProductRelation.objects.filter_active().filter(
                    order_id=OuterRef("id"),
                    product__donation_allowed=True,
                    status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
                )
            ),
            total_paid_price=Coalesce(
                Subquery(
                    total_paid_sq,
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                Value(0),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
        .filter(
            has_donation_product=True,
            current_status__in=REFUNDABLE_STATUSES,
        )
        .order_by("-total_paid_price", "created_at")
    )

    filterset_class = PatronFilterSet
    serializer_class = PatronSerializer
    authentication_classes = []


router = routers.SimpleRouter()
router.register("", PatronViewSet, basename="patron")
urlpatterns = router.urls
