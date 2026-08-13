from collections.abc import Callable
from re import compile
from typing import Any

from core.const.scancode import SCANCODE_ERROR_GUIDE, SCANCODE_MESSAGES
from core.const.tag import OpenAPITag
from core.negotiation import IgnoreClientContentNegotiation
from core.openapi.schemas import build_html_responses
from core.templatetags.i18n_extras import is_english
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, renderers, request, response, status, viewsets
from shop.order.models import Order, OrderProductRelation
from shop.order.serializers.scancode import (
    OrderProductScanCodeSerializer,
    OrderScanCodeSerializer,
    UserScanCodeSerializer,
)
from shop.payment_history.models import PaymentHistoryStatus
from user.models import UserExt


class _ScanCodeError(Exception):
    def __init__(self, key: str, code: int) -> None:
        super().__init__(key, code)
        self.key = key
        self.code = code

    def to_response(self) -> response.Response:
        lang, sub_lang = ("en", "ko") if is_english() else ("ko", "en")
        return response.Response(
            data={
                "error_msg": SCANCODE_MESSAGES[self.key][lang],
                "error_msg_sub": SCANCODE_MESSAGES[self.key][sub_lang],
                "error_guide": SCANCODE_ERROR_GUIDE[lang],
                "error_guide_sub": SCANCODE_ERROR_GUIDE[sub_lang],
            },
            status=self.code,
            template_name="scancode_error.html",
        )


def _render_user(token: str) -> response.Response:
    if not (user := UserExt.from_scancode_token(token)):
        raise _ScanCodeError(key="user_not_found", code=status.HTTP_403_FORBIDDEN)
    # 환불된 주문도 응답에 포함(현장 스태프의 이력 확인용). 단 모두 refunded 면 게이트.
    orders = list(Order.objects.filter_purchased_by(user).filter_in_last_six_months())
    if not any(o.current_status != PaymentHistoryStatus.refunded for o in orders):
        raise _ScanCodeError(key="user_no_valid_order", code=status.HTTP_403_FORBIDDEN)
    return response.Response(
        data={
            "user": UserScanCodeSerializer(instance=user).data,
            "orders": OrderScanCodeSerializer(instance=orders, many=True).data,
        },
        status=status.HTTP_200_OK,
        template_name="scancode_view_user.html",
    )


def _render_order(token: str) -> response.Response:
    if not (order := Order.from_scancode_token(token)):
        raise _ScanCodeError(key="order_not_found", code=status.HTTP_404_NOT_FOUND)
    if order.current_status == PaymentHistoryStatus.refunded:
        raise _ScanCodeError(key="order_refunded", code=status.HTTP_404_NOT_FOUND)
    return response.Response(
        data={"order": OrderScanCodeSerializer(instance=order).data},
        status=status.HTTP_200_OK,
        template_name="scancode_view_order.html",
    )


def _render_opr(token: str) -> response.Response:
    if not (opr := OrderProductRelation.from_scancode_token(token)):
        raise _ScanCodeError(key="opr_not_found", code=status.HTTP_403_FORBIDDEN)
    return response.Response(
        data={"order_product": OrderProductScanCodeSerializer(instance=opr).data},
        status=status.HTTP_200_OK,
        template_name="scancode_view_opr.html",
    )


_DISPATCH: dict[str, Callable[[str], response.Response]] = {
    "user": _render_user,
    "order": _render_order,
    "opr": _render_opr,
}
_SCANCODE_REGEX = compile(rf"^(?P<prefix>{'|'.join(_DISPATCH)}):(?P<short_id>[A-Za-z0-9]+):(?P<salt>[A-Za-z0-9_-]+)$")


class ScanCodeViewSet(viewsets.GenericViewSet):
    queryset = Order.objects.none()  # router 등록용 placeholder — 실제 lookup 은 token 으로.
    serializer_class = None
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    renderer_classes = [renderers.TemplateHTMLRenderer]
    content_negotiation_class = IgnoreClientContentNegotiation  # 스캐너 인앱 브라우저 Accept 로 406 이 나가지 않도록.

    @extend_schema(
        summary="QR 코드 페이지 (token 으로 dispatch)",
        tags=[OpenAPITag.SHOP_ORDER],
        parameters=[
            OpenApiParameter(name="token", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True)
        ],
        responses=(
            build_html_responses(names=["QR 코드가 포함된 HTML"], status_code=status.HTTP_200_OK)
            | build_html_responses(names=["인증 실패 HTML"], status_code=status.HTTP_403_FORBIDDEN)
            | build_html_responses(names=["대상을 찾을 수 없는 경우"], status_code=status.HTTP_404_NOT_FOUND)
        ),
    )
    def list(self, request: request.Request, *args: tuple[Any], **kwargs: dict[str, Any]) -> response.Response:
        try:
            if not (token := request.query_params.get("token")):
                raise _ScanCodeError(key="no_token", code=status.HTTP_404_NOT_FOUND)
            if not (match := _SCANCODE_REGEX.match(token)):
                raise _ScanCodeError(key="invalid_token", code=status.HTTP_404_NOT_FOUND)
            return _DISPATCH[match["prefix"]](token)
        except _ScanCodeError as e:
            return e.to_response()
