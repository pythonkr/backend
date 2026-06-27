from admin_api.dashboard import charts as _charts  # noqa: F401  레지스트리 등록 보장
from admin_api.dashboard.params import DashboardParams
from admin_api.dashboard.registry import CHART_REGISTRY
from admin_api.serializers.dashboard import (
    ChartDataRequestSerializer,
    ChartDefinitionResponseSerializer,
    MetricChartDataResponseSerializer,
    SeriesChartDataResponseSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema
from event.models import Event
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import ViewSet
from shop.product.models import Product


class DashboardChartAdminViewSet(ViewSet):
    permission_classes = [IsSuperUser]

    @extend_schema(
        summary="차트 목록",
        tags=[OpenAPITag.ADMIN_DASHBOARD],
        responses={HTTP_200_OK: ChartDefinitionResponseSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        ts = (
            Product.objects.filter_active()
            .filter(category__is_ticket=True)
            .order_by("category__priority", "name")
            .values("id", "name", "category__event_id")  # event_id: 프론트의 이벤트→티켓 종속 필터용
        )
        es = (
            Event.objects.filter_active()
            .filter(category__is_ticket=True)
            .values("id", "name", "stats_start_date", "stats_end_date")
            .distinct()
            .order_by("name")
        )
        dynamic_options = {
            "tickets": [
                {
                    "value": str(t["id"]),
                    "label": t["name"],
                    "event_id": t["category__event_id"] and str(t["category__event_id"]),
                }
                for t in ts
            ],
            "events": [
                {
                    "value": str(e["id"]),
                    "label": e["name"],
                    "date_from": e["stats_start_date"] and e["stats_start_date"].isoformat(),
                    "date_to": e["stats_end_date"] and e["stats_end_date"].isoformat(),
                }
                for e in es
            ],
        }
        return Response([handler.to_dict(dynamic_options) for handler in CHART_REGISTRY.values()])

    @extend_schema(
        summary="차트 데이터 조회",
        tags=[OpenAPITag.ADMIN_DASHBOARD],
        request=ChartDataRequestSerializer,
        responses={
            HTTP_200_OK: PolymorphicProxySerializer(
                component_name="ChartDataResponse",
                serializers=[MetricChartDataResponseSerializer, SeriesChartDataResponseSerializer],
                resource_type_field_name=None,  # discriminator 없는 순수 oneOf
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="data")
    def data(self, request: Request, pk: str | None = None) -> Response:
        if not (handler := CHART_REGISTRY.get(pk)):
            raise NotFound(f"Unknown chart: {pk}")

        params_serializer = handler.params_serializer(data=request.data.get("params") or {})
        params_serializer.is_valid(raise_exception=True)
        params = DashboardParams.from_validated(params_serializer.validated_data)
        return Response({"chart_id": pk, **handler.handle(params)})
