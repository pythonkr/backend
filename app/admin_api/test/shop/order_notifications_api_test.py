from urllib.parse import urljoin

import pytest
from django.conf import settings
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from shop.test.helpers import OrderNotificationsAdminApi


@pytest.mark.django_db
def test_notification_preview_rejects_non_superuser(customer_client):
    response = OrderNotificationsAdminApi(http_client=customer_client).preview({})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_notification_send_rejects_non_superuser(customer_client):
    response = OrderNotificationsAdminApi(http_client=customer_client).send({})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_notification_preview_returns_recipients_for_completed_order(api_client, completed_order, email_template):
    # email_template.data = `{"title":"Hi {{ name }}", ..., "send_to":"{{ recipient }}", "body":"Hello {{ name }}"}`
    # → template_variables = sorted({"name", "recipient"}).
    response = OrderNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(email_template.id)}
    )
    assert response.status_code == HTTP_200_OK
    scancode_url = urljoin(settings.BACKEND_DOMAIN, completed_order.scancode_path)
    assert response.json() == {
        "template_variables": ["name", "recipient"],
        "recipients": [
            {
                "recipient": "customer@example.com",
                "context": {"scancode_url": scancode_url},
                "missing_variables": ["name", "recipient"],
            }
        ],
    }


@pytest.mark.django_db
def test_notification_preview_rejects_unknown_template_id(api_client, completed_order):
    response = OrderNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        "errors": [{"code": "invalid", "detail": "Template not found.", "attr": "template_id"}],
    }


@pytest.mark.django_db
def test_notification_preview_excludes_refunded_orders(api_client, refunded_order, email_template):
    response = OrderNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(email_template.id)}
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"template_variables": ["name", "recipient"], "recipients": []}
