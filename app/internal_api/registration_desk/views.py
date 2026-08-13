import functools

from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from django.db import models, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import (
    Error403Serializer,
    Error404Serializer,
    ValidationErrorResponseSerializer,
)
from internal_api.models import RegistrationDeskConfig
from internal_api.registration_desk.filters import (
    RegistrationDeskOrderFilterSet,
    RegistrationDeskOrderProductFilterSet,
)
from internal_api.registration_desk.serializers import (
    OUT_OF_SCOPE_MESSAGE,
    RegistrationDeskConfigurationSerializer,
    RegistrationDeskOrderProductSerializer,
    RegistrationDeskOrderSerializer,
    RegistrationDeskSessionSerializer,
    RegistrationDeskStatisticsSerializer,
)
from rest_framework import decorators, exceptions, mixins, permissions, request, response, status, viewsets
from shop.order.models import Order, OrderProductRelation, OrderProductRelationTag
from shop.payment_history.models import PaymentHistory
from shop.serializers.refund import OrderProductRefundSerializer, OrderTotalRefundSerializer

NO_DESK_CONFIG_MESSAGE = "오늘 적용되는 등록 데스크 설정이 없습니다."


class CurrentDeskConfigMixin:
    """조회는 열어 두되 변경은 오늘 설정의 범위로 제한한다."""

    @functools.cached_property
    def current_config(self) -> RegistrationDeskConfig:
        queryset = RegistrationDeskConfig.objects.filter_active().select_related("event__logo")
        if not (config := queryset.filter_by_date().first()):
            raise exceptions.PermissionDenied(NO_DESK_CONFIG_MESSAGE)
        return config

    def assert_in_scope(self, order_product_relation_ids: list) -> None:
        if not self.current_config.covers(order_product_relation_ids):
            raise exceptions.PermissionDenied(OUT_OF_SCOPE_MESSAGE)


class RequiredFilterMixin:
    required_filter_params: tuple[str, ...] = ()
    exclusive_filter_params = False

    def list(self, request: request.Request, *args: object, **kwargs: object) -> response.Response:
        if not (provided := [p for p in self.required_filter_params if request.query_params.get(p, "").strip()]):
            joined = ", ".join(self.required_filter_params)
            raise exceptions.ValidationError(f"다음 조회 조건 중 하나 이상이 필요합니다: {joined}")
        if self.exclusive_filter_params and len(provided) > 1:
            joined = ", ".join(provided)
            raise exceptions.ValidationError(f"다음 조회 조건은 동시에 사용할 수 없습니다: {joined}")
        return super().list(request, *args, **kwargs)


@method_decorator(
    ensure_csrf_cookie, name="dispatch"
)  # 4xx 응답에도 CSRF 쿠키를 실어야 로그인 후 곧바로 PATCH/DELETE 를 보낼 수 있음
class RegistrationDeskViewSet(CurrentDeskConfigMixin, viewsets.ViewSet):
    permission_classes = [IsSuperUser]

    @extend_schema(
        summary="세션 조회",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskSessionSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    )
    @decorators.action(detail=False, methods=["get"])
    def session(self, req: request.Request) -> response.Response:
        return response.Response(RegistrationDeskSessionSerializer(req.user).data)

    @extend_schema(
        summary="데스크 설정 조회",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskConfigurationSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    )
    @decorators.action(detail=False, methods=["get"])
    def configuration(self, req: request.Request) -> response.Response:
        return response.Response(RegistrationDeskConfigurationSerializer(self.current_config).data)

    @extend_schema(
        summary="등록 통계 조회",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskStatisticsSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    )
    @decorators.action(detail=False, methods=["get"])
    def statistics(self, req: request.Request) -> response.Response:
        counts = (
            OrderProductRelation.objects.filter_active()
            .filter(status__in=OrderProductRelation.PURCHASED_STOCK_STATUS)
            .filter(
                order__in=Order.objects.filter_has_payment_histories(),
                product__deleted_at__isnull=True,
                product__category__deleted_at__isnull=True,
                product__category__is_ticket=True,
            )
            .filter(self.current_config.build_query())
            .aggregate(
                registration_target_count=models.Count("id"),
                registered_count=models.Count(
                    "id", filter=models.Q(status=OrderProductRelation.OrderProductStatus.used)
                ),
                waiting_count=models.Count("id", filter=models.Q(status=OrderProductRelation.OrderProductStatus.paid)),
            )
        )
        return response.Response(RegistrationDeskStatisticsSerializer(counts).data)


@extend_schema_view(
    list=extend_schema(
        summary="주문 검색",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskOrderSerializer(many=True),
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    ),
    partial_update=extend_schema(
        summary="주문 수정",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskOrderSerializer,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
            status.HTTP_404_NOT_FOUND: Error404Serializer,
        },
    ),
)
@method_decorator(name="partial_update", decorator=transaction.atomic)
class RegistrationDeskOrderViewSet(
    CurrentDeskConfigMixin,
    RequiredFilterMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Order.objects.filter_has_payment_histories()
        .select_related("customer_info")
        .with_dto_prefetches()
        .order_by("-created_at")
    )
    filterset_class = RegistrationDeskOrderFilterSet
    serializer_class = RegistrationDeskOrderSerializer
    pagination_class = AdminPagination
    permission_classes = [IsSuperUser]
    http_method_names = ["get", "patch", "delete"]
    required_filter_params = ("keywords", "order_id", "order_product_relation_id", "user_unique_id")

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        if self.request.method not in permissions.SAFE_METHODS:
            context["desk_config"] = self.current_config
        return context

    @extend_schema(
        summary="주문 전체 환불",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        parameters=[
            OpenApiParameter(
                name="otp",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                allow_blank=False,
                required=True,
                description="환불 승인자의 6자리 TOTP 코드",
            ),
        ],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
            status.HTTP_404_NOT_FOUND: Error404Serializer,
        },
    )
    @decorators.action(detail=True, methods=["delete"], url_path="refund")
    @transaction.atomic
    def refund(self, req: request.Request, pk: str | None = None) -> response.Response:
        order = self.get_object()
        # 전체 환불은 활성 상품 전부를 건드린다.
        self.assert_in_scope([product.id for product in order.active_products])
        serializer = OrderTotalRefundSerializer(
            instance=order,
            data={"totp": req.query_params.get("otp")},
            context={"check_refundable_date": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="주문 상품 조회",
        description="`order_product_relation_id` 또는 `scancode` 중 정확히 하나를 전달해야 한다.",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        responses={
            status.HTTP_200_OK: RegistrationDeskOrderProductSerializer(many=True),
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
        },
    ),
)
class RegistrationDeskOrderProductViewSet(
    CurrentDeskConfigMixin, RequiredFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = (
        OrderProductRelation.objects.filter_active()
        .filter(order__in=Order.objects.filter_has_payment_histories())
        .select_related("product", "product__category", "order", "ticket_info")
        .prefetch_active_options()
        .prefetch_related(
            models.Prefetch(
                "order__payment_histories",
                queryset=PaymentHistory.objects.filter_active(),
                to_attr="_active_payment_histories",
            ),
            models.Prefetch("tags", queryset=OrderProductRelationTag.objects.filter_active()),
        )
        .order_by("-created_at")
    )
    serializer_class = RegistrationDeskOrderProductSerializer
    filterset_class = RegistrationDeskOrderProductFilterSet
    pagination_class = AdminPagination
    permission_classes = [IsSuperUser]
    required_filter_params = ("order_product_relation_id", "scancode")
    exclusive_filter_params = True

    @extend_schema(
        summary="주문 상품 부분 환불",
        tags=[OpenAPITag.EXT_REGISTRATION_DESK_API],
        parameters=[
            OpenApiParameter(
                name="otp",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                allow_blank=False,
                required=True,
                description="환불 승인자의 6자리 TOTP 코드",
            ),
        ],
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
            status.HTTP_403_FORBIDDEN: Error403Serializer,
            status.HTTP_404_NOT_FOUND: Error404Serializer,
        },
    )
    @decorators.action(detail=True, methods=["delete"], url_path="refund")
    @transaction.atomic
    def refund(self, req: request.Request, pk: str | None = None) -> response.Response:
        order_product = self.get_object()
        self.assert_in_scope([order_product.id])
        serializer = OrderProductRefundSerializer(
            instance=order_product,
            data={"totp": req.query_params.get("otp")},
            context={"check_refundable_date": False},
        )
        serializer.is_valid(raise_exception=True)
        serializer.refund()
        return response.Response(status=status.HTTP_204_NO_CONTENT)
