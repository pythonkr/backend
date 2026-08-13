import datetime
import io
import typing
from codecs import BOM_UTF8
from logging import getLogger

import pandas
from admin_api.filtersets.shop.order_products import OrderProductRelationAdminFilterSet
from admin_api.filtersets.shop.orders import OrderAdminFilterSet
from admin_api.serializers.shop.orders import (
    OrderAdminSerializer,
    OrderExportRequestSerializer,
    OrderProductRelationTagAdminSerializer,
    OrderProductRelationTagAssignResultSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.util.fileutil import read_uploaded_csv
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from django.core.files import File
from django.db import models, transaction
from django.http.response import HttpResponse, StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import ValidationErrorResponseSerializer
from rest_framework import exceptions, mixins, parsers, request, response, status, viewsets
from rest_framework.decorators import action
from shop.order import exports, imports
from shop.order.models import Order, OrderProductRelation, OrderProductRelationTag
from shop.payment_history.models import PURCHASED_STATUSES, REFUNDABLE_STATUSES, PaymentHistory
from shop.product.models import Product
from shop.serializers.refund import OrderProductRefundSerializer, OrderTotalRefundSerializer

logger = getLogger(__name__)

ADMIN_METHODS = ["list", "retrieve", "partial_update"]


# OrderProductRelation + nested Options prefetch — `Order.products` 용.
_OPR_PREFETCH_QS = (
    OrderProductRelation.objects.filter_active()
    .select_related("product", "ticket_info")
    .prefetch_active_options()
    .prefetch_related(models.Prefetch("tags", queryset=OrderProductRelationTag.objects.filter_active()))
)

_TAGGABLE_ORDER_PRODUCT_QS = (
    OrderProductRelation.objects.filter_active()
    .filter(order__isnull=False)
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
)

_OPR_FILTER_PARAMETERS = [
    OpenApiParameter(name=name, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY)
    for name in OrderProductRelationAdminFilterSet.Meta.fields
]

# `Order.payment_histories` 용 prefetch — 최신순.
_PAYMENT_HISTORY_PREFETCH_QS = PaymentHistory.objects.filter_active().order_by("-created_at")


def _payment_history_created_at_subquery(*, latest: bool) -> models.Subquery:
    """Order 별 첫/마지막 PaymentHistory.created_at scalar subquery (filter/annotate 양쪽 용)."""
    return models.Subquery(
        PaymentHistory.objects.filter_active()
        .filter(order_id=models.OuterRef("pk"))
        .order_by("-created_at" if latest else "created_at")
        .values("created_at")[:1]
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_ORDER]) for m in ADMIN_METHODS})
class OrderAdminViewSet(
    JsonSchemaMixin,
    SelectablesMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch"]
    serializer_class = OrderAdminSerializer
    filterset_class = OrderAdminFilterSet
    permission_classes = [IsSuperUser]
    queryset = (
        Order.objects.filter_has_payment_histories()
        .filter(models.Exists(OrderProductRelation.objects.filter_active().filter(order=models.OuterRef("pk"))))
        .select_related_with_user("user", "customer_info")
        .prefetch_related(
            models.Prefetch("products", queryset=_OPR_PREFETCH_QS),
            models.Prefetch("payment_histories", queryset=_PAYMENT_HISTORY_PREFETCH_QS),
        )
        .annotate(
            current_status=PaymentHistory.objects.latest_per_order_field("status"),
            latest_imp_id=PaymentHistory.objects.latest_per_order_field("imp_id"),
            latest_price=PaymentHistory.objects.latest_per_order_field("price"),
            first_paid_at=_payment_history_created_at_subquery(latest=False),
            status_changed_at=_payment_history_created_at_subquery(latest=True),
        )
        .order_by(models.F("first_paid_at").desc(nulls_last=True), "-created_at", "pk")
    )

    @extend_schema(
        summary="주문 전체 환불",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER_REFUND],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="refund")
    @transaction.atomic
    def refund(self, request: request.Request, pk: typing.Any = None) -> response.Response:
        serializer = OrderTotalRefundSerializer(
            instance=self.get_object(),
            data={},
            context={"check_refundable_date": False, "check_totp": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="주문 부분 환불",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER_REFUND],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path=r"products/(?P<rel_id>[^/.]+)/refund")
    @transaction.atomic
    def refund_product(
        self,
        request: request.Request,
        pk: typing.Any = None,
        rel_id: typing.Any = None,
    ) -> response.Response:
        order_product_rel = OrderProductRelation.objects.filter_active().filter(order_id=pk, id=rel_id).first()
        if not order_product_rel:
            raise exceptions.NotFound("OrderProductRelation not found.")

        serializer = OrderProductRefundSerializer(
            instance=order_product_rel,
            data={},
            context={"check_refundable_date": False, "check_totp": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="주문 CSV 가져오기 템플릿 다운로드",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER],
        parameters=[OpenApiParameter(name="product_id", type=OpenApiTypes.UUID, required=True)],
        responses={status.HTTP_200_OK: OpenApiTypes.STR},
    )
    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request: request.Request) -> HttpResponse:
        if not (product_id := request.query_params.get("product_id")):
            raise exceptions.ValidationError({"product_id": "이 값이 필요합니다."})
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist as e:
            raise exceptions.NotFound("Product not found") from e

        csv_content = imports.OrderProductImportSerializer.get_template_csv(product=product)
        return HttpResponse(
            content=BOM_UTF8.decode("utf-8") + csv_content,
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=order_import_template.csv"},
        )

    @extend_schema(
        summary="주문 CSV 가져오기",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"csv_file": {"type": "string", "format": "binary"}},
            }
        },
        responses={
            status.HTTP_201_CREATED: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[parsers.MultiPartParser],
    )
    @transaction.atomic
    def import_csv(self, request: request.Request) -> response.Response:
        if not (csv_file := request.FILES.get("csv_file")):
            raise exceptions.ValidationError({"csv_file": "이 값이 필요합니다."})

        csv_df = read_uploaded_csv(csv_file.read()).fillna("")
        csv_serializers = [
            imports.OrderProductImportSerializer(data=datum) for datum in csv_df.to_dict(orient="index").values()
        ]
        # 모든 serializer 의 .is_valid() 를 호출하기 위해 list comprehension 사용 (all() 의 short-circuit 회피).
        if not all([s.is_valid() for s in csv_serializers]):
            raise exceptions.ValidationError([s.errors for s in csv_serializers])
        for s in csv_serializers:
            s.save()
        return response.Response(status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="주문 XLSX 내보내기",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER],
        parameters=[
            OpenApiParameter(name="event_id", description="이벤트 ID (CSV 다중값)"),
            OpenApiParameter(name="category_group_id", description="카테고리 그룹 ID (CSV 다중값)"),
            OpenApiParameter(name="category_id", description="카테고리 ID (CSV 다중값)"),
            OpenApiParameter(name="product_id", description="상품 ID (CSV 다중값)"),
            OpenApiParameter(
                name="include_refunded", type=OpenApiTypes.BOOL, description="환불 주문 포함 여부 (기본 false)"
            ),
        ],
        request=None,
        responses={status.HTTP_200_OK: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["post"], url_path="export")
    def export(self, request: request.Request) -> StreamingHttpResponse:
        req = OrderExportRequestSerializer(data=request.query_params)
        req.is_valid(raise_exception=True)
        statuses = PURCHASED_STATUSES if req.validated_data["include_refunded"] else REFUNDABLE_STATUSES

        base_qs = (
            Order.objects.filter_active()
            .select_related("user")
            .with_dto_prefetches()
            .annotate(
                current_status=PaymentHistory.objects.latest_per_order_field("status"),
                latest_imp_id=PaymentHistory.objects.latest_per_order_field("imp_id"),
                latest_price=PaymentHistory.objects.latest_per_order_field("price"),
                first_paid_at=_payment_history_created_at_subquery(latest=False),
                status_changed_at=_payment_history_created_at_subquery(latest=True),
            )
            .filter(current_status__in=statuses)
        )
        order_qs = OrderAdminFilterSet(request.query_params, queryset=base_qs, request=request).qs
        order_product_qs = (
            OrderProductRelation.objects.filter_active()
            .filter(order__in=order_qs)
            .select_related("product")
            .prefetch_active_options()
            .distinct()
        )

        filename = f"order_export_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        fileio = io.BytesIO()
        df_dict: dict[str, pandas.DataFrame] = {
            "주문": exports.OrderExportSerializer(instance=order_qs, many=True).export(),
            "주문상품": exports.OrderProductExportSerializer(instance=order_product_qs, many=True).export(),
        }
        # engine 명시 — pandas 의 "auto" 는 설치된 패키지에 따라 openpyxl 로 바뀔 수 있고,
        # autofit_columns 는 xlsxwriter 의 set_column API 에 의존한다.
        with pandas.ExcelWriter(fileio, engine="xlsxwriter") as writer:
            for sheet_name, df in df_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, startrow=0, startcol=0)
                exports.autofit_columns(writer.sheets[sheet_name], df)
        return StreamingHttpResponse(
            streaming_content=File(fileio),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@extend_schema_view(
    **{
        m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_ORDER_PRODUCT_TAG])
        for m in ["list", "retrieve", "create", "update", "partial_update", "destroy"]
    }
)
class OrderProductRelationTagAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = OrderProductRelationTagAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = OrderProductRelationTag.objects.filter_active().select_related_with_user()

    def _target_order_product_ids(self, req: request.Request) -> list:
        # 빈 값은 django-filter 가 무시하므로 `?id=` 같은 요청이 전체 태깅으로 이어지지 않도록 값까지 확인한다.
        if not any(req.query_params.get(name, "").strip() for name in OrderProductRelationAdminFilterSet.base_filters):
            joined = ", ".join(OrderProductRelationAdminFilterSet.base_filters)
            raise exceptions.ValidationError(f"대상을 좁힐 조회 조건이 하나 이상 필요합니다: {joined}")
        filterset = OrderProductRelationAdminFilterSet(
            req.query_params, queryset=_TAGGABLE_ORDER_PRODUCT_QS, request=req
        )
        if not filterset.is_valid():
            raise exceptions.ValidationError(filterset.errors)
        return list(filterset.qs.values_list("id", flat=True))

    @extend_schema(
        summary="주문 상품에 태그 부착 (filterset 으로 대상 지정)",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER_PRODUCT_TAG],
        parameters=_OPR_FILTER_PARAMETERS,
        request=None,
        responses={status.HTTP_200_OK: OrderProductRelationTagAssignResultSerializer},
    )
    @action(detail=True, methods=["post"])
    def assign(self, request: request.Request, pk: str | None = None) -> response.Response:
        target_ids = self._target_order_product_ids(request)
        self.get_object().order_product_relations.add(*target_ids)
        return response.Response({"affected": len(target_ids)})

    @extend_schema(
        summary="주문 상품에서 태그 해제 (filterset 으로 대상 지정)",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER_PRODUCT_TAG],
        parameters=_OPR_FILTER_PARAMETERS,
        request=None,
        responses={status.HTTP_200_OK: OrderProductRelationTagAssignResultSerializer},
    )
    @action(detail=True, methods=["post"])
    def unassign(self, request: request.Request, pk: str | None = None) -> response.Response:
        target_ids = self._target_order_product_ids(request)
        self.get_object().order_product_relations.remove(*target_ids)
        return response.Response({"affected": len(target_ids)})
