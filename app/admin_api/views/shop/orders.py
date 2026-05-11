import datetime
import io
import json
import typing
from logging import getLogger

import pandas
from admin_api.filtersets.shop.orders import OrderAdminFilterSet
from admin_api.serializers.shop.orders import OrderAdminSerializer, OrderExportRequestSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.util.totp import TOTPInfo
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.conf import settings
from django.core.files import File
from django.db import models, transaction
from django.http.response import StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import exceptions, parsers, request, response, status, viewsets
from rest_framework.decorators import action
from shop.order import exports, imports
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PURCHASED_STATUSES, REFUNDABLE_STATUSES, PaymentHistory
from shop.product.models import Product
from shop.serializers.refund import OrderTotalRefundSerializer

logger = getLogger(__name__)

ADMIN_METHODS = ["list", "retrieve"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_SHOP_ORDER]) for m in ADMIN_METHODS})
class OrderAdminViewSet(JsonSchemaViewSet, viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "post"]
    serializer_class = OrderAdminSerializer
    filterset_class = OrderAdminFilterSet
    permission_classes = [IsSuperUser]
    queryset = (
        Order.objects.filter_active()
        .select_related_with_user("user", "customer_info")
        .prefetch_related(
            models.Prefetch(
                "products",
                queryset=OrderProductRelation.objects.filter_active()
                .select_related("product")
                .prefetch_related(
                    models.Prefetch(
                        "options",
                        queryset=OrderProductOptionRelation.objects.filter_active().select_related(
                            "product_option_group",
                            "product_option",
                        ),
                    ),
                ),
            ),
            models.Prefetch(
                "payment_histories",
                queryset=PaymentHistory.objects.filter_active().order_by("-created_at"),
                to_attr="_payment_histories_by_latest",
            ),
        )
        .annotate(
            current_status=PaymentHistory.objects.latest_per_order_field("status"),
            latest_imp_id=PaymentHistory.objects.latest_per_order_field("imp_id"),
            latest_price=PaymentHistory.objects.latest_per_order_field("price"),
        )
        .order_by("-created_at")
    )

    @extend_schema(
        summary="주문 전체 환불 (환불 승인자 TOTP 필수)",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER_REFUND],
        parameters=[OpenApiParameter(name="otp", location=OpenApiParameter.QUERY, required=True)],
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @action(detail=True, methods=["post"], url_path="refund")
    @transaction.atomic
    def refund(self, request: request.Request, pk: typing.Any = None) -> response.Response:
        if not (otp := request.query_params.get("otp")):
            raise exceptions.NotAuthenticated("환불 승인자의 OTP 코드가 필요합니다.")
        if not TOTPInfo(key=settings.SHOP.refund_authorizer_secret_key.encode()).check(otp):
            raise exceptions.PermissionDenied("OTP 코드가 올바르지 않습니다.")

        serializer = OrderTotalRefundSerializer(
            instance=self.get_object(),
            data={"check_refundable_date": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="주문 CSV 가져오기 템플릿 다운로드",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER],
        parameters=[
            OpenApiParameter(name="product_id", type=OpenApiTypes.UUID, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={status.HTTP_200_OK: OpenApiTypes.STR},
    )
    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request: request.Request) -> response.Response:
        if not (product_id := request.query_params.get("product_id")):
            raise exceptions.ValidationError({"product_id": "이 값이 필요합니다."})
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist as e:
            raise exceptions.NotFound("Product not found") from e

        return response.Response(
            data=imports.OrderProductImportSerializer.get_template_csv(product=product),
            content_type="text/csv",
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
        responses={status.HTTP_201_CREATED: None},
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

        csv_io = io.StringIO(csv_file.read().decode("utf-8"))
        csv_df = pandas.read_csv(csv_io)
        csv_serializers = [
            imports.OrderProductImportSerializer(data=datum) for datum in csv_df.to_dict(orient="index").values()
        ]
        # 모든 serializer 의 .is_valid() 를 호출하기 위해 list comprehension 사용 (all() 의 short-circuit 회피).
        if not all([s.is_valid() for s in csv_serializers]):
            errors = [s.errors for s in csv_serializers]
            return response.Response(
                data=json.loads(json.dumps(errors, ensure_ascii=False)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        for s in csv_serializers:
            s.save()
        return response.Response(status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="주문 XLSX 내보내기",
        tags=[OpenAPITag.ADMIN_SHOP_ORDER],
        request=OrderExportRequestSerializer,
        responses={status.HTTP_200_OK: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["post"], url_path="export")
    def export(self, request: request.Request) -> StreamingHttpResponse:
        req = OrderExportRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        product_ids = req.validated_data["product_ids"]
        include_refunded = req.validated_data["include_refunded"]

        statuses = PURCHASED_STATUSES if include_refunded else REFUNDABLE_STATUSES

        order_qs = (
            Order.objects.annotate(current_status=PaymentHistory.objects.latest_per_order_field("status"))
            .select_related("user")
            .prefetch_related("products", "payment_histories")
            .filter(products__product_id__in=product_ids, current_status__in=statuses)
        )
        order_product_qs = (
            OrderProductRelation.objects.filter(order__in=order_qs)
            .select_related("product")
            .prefetch_related("options__product_option_group", "options__product_option")
            .distinct()
        )

        filename = f"order_export_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        fileio = io.BytesIO()
        df_dict: dict[str, pandas.DataFrame] = {
            "주문": exports.OrderExportSerializer(instance=order_qs, many=True).export(),
            "주문상품": exports.OrderProductExportSerializer(instance=order_product_qs, many=True).export(),
        }
        with pandas.ExcelWriter(fileio) as writer:
            for sheet_name, df in df_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, startrow=0, startcol=0)
        return StreamingHttpResponse(
            streaming_content=File(fileio),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
