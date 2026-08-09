from admin_api.filtersets.shop.order_products import OrderProductRelationAdminFilterSet
from admin_api.filtersets.shop.orders import OrderAdminFilterSet
from admin_api.serializers.notification import (
    EmailNotificationHistoryAdminSerializer,
    NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer,
    NHNCloudSMSNotificationHistoryAdminSerializer,
)
from admin_api.serializers.shop.orders import (
    OrderProductSendNotificationSerializer,
    OrderSendNotificationPreviewResponseSerializer,
    OrderSendNotificationSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.openapi.schemas import build_html_responses
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from django.db import models
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_view
from rest_framework import request, response, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import StaticHTMLRenderer
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PURCHASED_STATUSES, PaymentHistory

ACTION_METHODS = ["preview", "render_preview", "send"]


def _schema(summaries: dict[str, str]) -> dict:
    return {m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_ORDER], summary=summaries[m]) for m in ACTION_METHODS}


_SEND_HISTORY_RESPONSE = PolymorphicProxySerializer(
    component_name="OrderSendNotificationHistory",
    serializers=[
        EmailNotificationHistoryAdminSerializer,
        NHNCloudSMSNotificationHistoryAdminSerializer,
        NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer,
    ],
    resource_type_field_name=None,
)


class _NotificationSendMixin(JsonSchemaMixin, SelectablesMixin, viewsets.GenericViewSet):
    http_method_names = ["post"]
    permission_classes = [IsSuperUser]

    @extend_schema(responses={status.HTTP_200_OK: OrderSendNotificationPreviewResponseSerializer})
    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request: request.Request) -> response.Response:
        req = self.get_serializer(instance=self.filter_queryset(self.get_queryset()), data=request.data)
        req.is_valid(raise_exception=True)
        return response.Response(data=req.build_preview_response().data, status=status.HTTP_200_OK)

    @extend_schema(responses=build_html_responses(names=["Order Notification Render Preview"]))
    @action(detail=False, methods=["post"], url_path="render", renderer_classes=[StaticHTMLRenderer])
    def render_preview(self, request: request.Request) -> response.Response:
        req = self.get_serializer(instance=self.filter_queryset(self.get_queryset()), data=request.data)
        req.is_valid(raise_exception=True)
        return response.Response(data=req.build_rendered_html())

    @extend_schema(responses={status.HTTP_201_CREATED: _SEND_HISTORY_RESPONSE})
    @action(detail=False, methods=["post"], url_path="send")
    def send(self, request: request.Request) -> response.Response:
        req = self.get_serializer(instance=self.filter_queryset(self.get_queryset()), data=request.data)
        req.is_valid(raise_exception=True)
        return response.Response(data=req.build_send_response().data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    **_schema(
        {
            "preview": "주문 알림 발송 dry-run (recipient + context + missing_variables 조회)",
            "render_preview": "주문 알림 렌더 미리보기 (첫 대상 기준 HTML)",
            "send": "주문 알림 발송 (filterset 으로 대상 주문 지정, 결제까지 간 주문만)",
        }
    )
)
class OrderNotificationAdminViewSet(_NotificationSendMixin):
    """주문 단위 발송 — 주문 1건당 알림 1건. 수신처는 주문자.

    구매자에게 보내는 알림은 전부 이쪽 담당 — 상품 단위 발송은 항상 참가자에게 간다.
    """

    filterset_class = OrderAdminFilterSet
    serializer_class = OrderSendNotificationSerializer
    # 환불 주문도 포함 — 환불 안내처럼 환불 이후에 보내야 하는 알림이 있다.
    queryset = (
        Order.objects.filter_active()
        .annotate(current_status=PaymentHistory.objects.latest_per_order_field("status"))
        .filter(current_status__in=PURCHASED_STATUSES)
        .select_related("customer_info")
        .prefetch_related(
            Order.prefetchs["_active_payment_histories"],
            models.Prefetch(
                "products",
                queryset=OrderProductRelation.objects.filter_active().prefetch_active_options(),
            ),
        )
    )


@extend_schema_view(
    **_schema(
        {
            "preview": "주문 상품 알림 발송 dry-run (recipient + context + missing_variables 조회)",
            "render_preview": "주문 상품 알림 렌더 미리보기 (첫 대상 기준 HTML)",
            "send": "주문 상품 알림 발송 (filterset 으로 대상 상품 지정, 상품별 QR)",
        }
    )
)
class OrderProductNotificationAdminViewSet(_NotificationSendMixin):
    """상품(OPR) 단위 발송 — 티켓 N 장이면 알림 N 건. 수신처는 참가자, `scancode_url` 은 상품 QR."""

    filterset_class = OrderProductRelationAdminFilterSet
    serializer_class = OrderProductSendNotificationSerializer
    queryset = (
        OrderProductRelation.objects.filter_active()
        .filter(order__isnull=False, status__in=OrderProductRelation.PURCHASED_OR_REFUNDED_STATUS)
        .annotate(
            order_current_status=PaymentHistory.objects.latest_per_order_field("status", outer_field="order_id"),
            order_latest_imp_id=PaymentHistory.objects.latest_per_order_field("imp_id", outer_field="order_id"),
            order_first_paid_at=(
                PaymentHistory.objects.filter_active()
                .filter(order_id=models.OuterRef("order_id"))
                .order_by("created_at")
                .values("created_at")[:1]
            ),
        )
        # 상품 가드와 짝을 맞추지 않으면 환불 대상이 부분 환불 주문에만 걸린다.
        .filter(order_current_status__in=PURCHASED_STATUSES)
        .select_related("product__category__event", "order", "order__customer_info", "ticket_info")
        .prefetch_active_options()
        .prefetch_related(
            # order.build_notification_context() 의 first_paid_at/first_paid_price 용.
            models.Prefetch(
                "order__payment_histories",
                queryset=PaymentHistory.objects.filter_active(),
                to_attr="_active_payment_histories",
            ),
            models.Prefetch(
                "order__products",
                queryset=OrderProductRelation.objects.filter_active(),
                to_attr="_active_products",
            ),
        )
        .order_by("order__created_at", "created_at", "pk")
    )
