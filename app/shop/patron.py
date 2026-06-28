from core.const.tag import OpenAPITag
from django.db.models import CharField, DecimalField, Exists, F, OuterRef, Subquery, Sum, TextField, Value
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, routers, serializers, status, viewsets
from shop.order.models import Order, OrderProductRelation, TicketInfo
from shop.payment_history.models import REFUNDABLE_STATUSES, PaymentHistory


class PatronFilterSet(filters.FilterSet):
    year = filters.NumberFilter(field_name="created_at__year")

    class Meta:
        model = Order
        fields = ["year"]


class PatronSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="customer_info.name", allow_null=True)
    contribution_message = serializers.CharField(read_only=True)

    class Meta:
        fields: list[str] = ["name", "contribution_message"]
        model = Order


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
    contribution_message_sq = (
        TicketInfo.objects.filter_active()
        .filter(order_product_relation__order_id=OuterRef("id"), order_product_relation__deleted_at__isnull=True)
        .exclude(contribution_message__isnull=True)
        .exclude(contribution_message="")
        .values("contribution_message")[:1]
    )

    queryset = (
        Order.objects.filter_active()
        .annotate(
            current_status=Subquery(latest_status_sq, output_field=CharField()),
            contribution_message=Coalesce(
                Subquery(contribution_message_sq, output_field=TextField()),
                Value(""),
                output_field=TextField(),
            ),
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
