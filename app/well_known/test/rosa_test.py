import http

from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient


def test_rosa_discovery_is_available_without_authentication():
    response = APIClient().get(reverse("rosa"))

    assert response.status_code == http.HTTPStatus.OK
    assert response.json() == {
        "schema_version": "1.0",
        "service": "rosa",
        "api": {
            "base_url": "/v1/internal-api/registration-desk/",
            "openapi_url": "/api/schema/v1/",
        },
        "authentication": {
            "type": "session",
            "session_url": "/v1/internal-api/registration-desk/session/",
            "login": {
                "type": "password",
                "method": "POST",
                "url": "/authn/social/browser/v1/auth/login",
                "identifier_field": "email",
                "password_field": "password",
            },
            "logout_url": "/authn/social/browser/v1/auth/session",
            "logout_method": "DELETE",
            "csrf": {
                "cookie_name": settings.CSRF_COOKIE_NAME,
                "header_name": "X-CSRFToken",
            },
        },
        "routes": {
            "retrieve_configuration": {"method": "GET", "path": "configuration/"},
            "retrieve_statistics": {"method": "GET", "path": "statistics/"},
            "list_orders": {"method": "GET", "path": "orders/"},
            "modify_order": {"method": "PATCH", "path": "orders/{id}/"},
            "refund_order": {"method": "DELETE", "path": "orders/{id}/refund/"},
            "list_order_products": {"method": "GET", "path": "order-products/"},
            "refund_order_product": {"method": "DELETE", "path": "order-products/{id}/refund/"},
        },
    }
