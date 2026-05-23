from admin_api.filtersets.shop.orders import OrderAdminFilterSet
from admin_api.serializers.notification import (
    EmailNotificationHistoryAdminSerializer,
    NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer,
    NHNCloudSMSNotificationHistoryAdminSerializer,
)
from admin_api.serializers.shop.orders import (
    OrderSendNotificationPreviewResponseSerializer,
    OrderSendNotificationSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db import models
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_view
from rest_framework import request, response, status, viewsets
from rest_framework.decorators import action
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import REFUNDABLE_STATUSES, PaymentHistory

ACTION_METHODS = ["preview", "send"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_ORDER]) for m in ACTION_METHODS})
class OrderNotificationAdminViewSet(JsonSchemaViewSet, viewsets.GenericViewSet):
    http_method_names = ["post"]
    permission_classes = [IsSuperUser]
    filterset_class = OrderAdminFilterSet
    serializer_class = OrderSendNotificationSerializer
    # 발송 가능 상태(REFUNDABLE_STATUSES) 만 baked-in — admin 이 `?status=refunded` 등을 넘겨도 교집합 0건으로 보호.
    queryset = (
        Order.objects.filter_active()
        .annotate(current_status=PaymentHistory.objects.latest_per_order_field("status"))
        .filter(current_status__in=REFUNDABLE_STATUSES)
        .select_related("customer_info")
        .prefetch_related(
            Order.prefetchs["_payment_histories_by_latest"],
            models.Prefetch(
                "products",
                queryset=OrderProductRelation.objects.filter_active().prefetch_related(
                    models.Prefetch(
                        "options",
                        queryset=OrderProductOptionRelation.objects.filter_active().select_related(
                            "product_option_group",
                            "product_option",
                        ),
                    ),
                ),
            ),
        )
    )

    @extend_schema(
        summary="주문 알림 발송 dry-run (recipient + context + missing_variables 조회)",
        responses={status.HTTP_200_OK: OrderSendNotificationPreviewResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request: request.Request) -> response.Response:
        req = self.get_serializer(instance=self.filter_queryset(self.get_queryset()), data=request.data)
        req.is_valid(raise_exception=True)
        return response.Response(data=req.build_preview_response().data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="주문 알림 발송 (filterset 으로 대상 주문 지정, 환불 가능 상태만)",
        responses={
            status.HTTP_201_CREATED: PolymorphicProxySerializer(
                component_name="OrderSendNotificationHistory",
                serializers=[
                    EmailNotificationHistoryAdminSerializer,
                    NHNCloudSMSNotificationHistoryAdminSerializer,
                    NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer,
                ],
                resource_type_field_name=None,
            ),
        },
    )
    @action(detail=False, methods=["post"], url_path="send")
    def send(self, request: request.Request) -> response.Response:
        req = self.get_serializer(instance=self.filter_queryset(self.get_queryset()), data=request.data)
        req.is_valid(raise_exception=True)
        return response.Response(data=req.build_send_response().data, status=status.HTTP_201_CREATED)
