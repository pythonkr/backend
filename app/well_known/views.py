from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# reverse 는 실제 인자를 요구하므로 sentinel 로 만든 뒤 placeholder 로 치환한다.
_ARG_SENTINEL = "00000000-0000-0000-0000-000000000000"

_ROSA_ROUTES = (
    ("retrieve_configuration", "GET", "desk-configuration", None),
    ("retrieve_statistics", "GET", "desk-statistics", None),
    ("list_orders", "GET", "orders-list", None),
    ("modify_order", "PATCH", "orders-detail", "{id}"),
    ("refund_order", "DELETE", "orders-refund", "{id}"),
    ("list_order_products", "GET", "order-products-list", None),
    ("refund_order_product", "DELETE", "order-products-refund", "{id}"),
)


def _registration_desk_url(url_name: str, placeholder: str | None = None) -> str:
    url = reverse(f"v1:registration_desk:{url_name}", args=[_ARG_SENTINEL] if placeholder else [])
    return url.replace(_ARG_SENTINEL, placeholder) if placeholder else url


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def retrieve_rosa_discovery(request: HttpRequest) -> Response:
    base_url = _registration_desk_url("desk-configuration").removesuffix("configuration/")
    session_url = _registration_desk_url("desk-session")

    return Response(
        data={
            "schema_version": "1.0",
            "service": "rosa",
            "api": {
                "base_url": base_url,
                "openapi_url": reverse("v1-schema"),
            },
            "authentication": {
                "type": "session",
                "session_url": session_url,
                "login": {
                    "type": "password",
                    "method": "POST",
                    "url": reverse("headless:browser:account:login"),
                    "identifier_field": "email",
                    "password_field": "password",
                },
                "logout_url": reverse("headless:browser:account:current_session"),
                "logout_method": "DELETE",
                "csrf": {
                    "cookie_name": settings.CSRF_COOKIE_NAME,
                    "header_name": "X-CSRFToken",
                },
            },
            "routes": {
                key: {
                    "method": method,
                    "path": _registration_desk_url(url_name, placeholder).removeprefix(base_url),
                }
                for key, method, url_name, placeholder in _ROSA_ROUTES
            },
        }
    )
