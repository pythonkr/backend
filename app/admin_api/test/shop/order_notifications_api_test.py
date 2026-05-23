from urllib.parse import urljoin

import pytest
from django.conf import settings
from notification.models.email import EmailNotificationHistory, EmailNotificationTemplate
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
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
def test_notification_preview_returns_recipients_for_completed_order(api_client, completed_order, order_email_template):
    response = OrderNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(order_email_template.id)}
    )
    assert response.status_code == HTTP_200_OK
    scancode_url = urljoin(settings.BACKEND_DOMAIN, completed_order.scancode_path)
    # 서버에서 isoformat 문자열로 변환된 채로 응답 / DB 저장 (JSONField datetime 미지원 회피).
    first_paid_at_str = completed_order.first_paid_at.isoformat()
    assert response.json() == {
        "template_variables": ["customer_email", "customer_name", "first_paid_price", "order_name"],
        "recipients": [
            {
                "recipient": "customer@example.com",
                "context": {
                    "scancode_url": scancode_url,
                    "order_name": "파이콘 한국 2026 티켓",
                    "first_paid_at": first_paid_at_str,
                    "first_paid_price": 10000,
                    "customer_name": "홍길동",
                    "customer_phone": "01012345678",
                    "customer_email": "customer@example.com",
                },
                "missing_variables": [],
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
def test_notification_preview_excludes_refunded_orders(api_client, refunded_order, order_email_template):
    response = OrderNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(order_email_template.id)}
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "template_variables": ["customer_email", "customer_name", "first_paid_price", "order_name"],
        "recipients": [],
    }


@pytest.mark.django_db
def test_notification_send_creates_history_for_completed_order(api_client, completed_order, order_email_template):
    # order_email_template 의 모든 변수가 Order 에서 자동 추출되므로 context_override 불필요.
    response = OrderNotificationsAdminApi(http_client=api_client).send(
        {"channel": "email", "template_id": str(order_email_template.id)}
    )
    assert response.status_code == HTTP_201_CREATED

    # NotificationHistoryBase.send() 의 Celery dispatch 는 on_commit 등록만 — test transaction rollback 으로 fire 안 됨.
    # 즉 SentTo 레코드까지 생성됐는지로 endpoint contract 확인.
    history_id = response.json()["id"]
    history = EmailNotificationHistory.objects.get(id=history_id)
    assert history.template_id == order_email_template.id
    assert history.sent_to_list.filter(recipient="customer@example.com").exists()


@pytest.mark.django_db
def test_notification_send_rejects_when_recipients_have_missing_template_variables(
    api_client, completed_order, superuser
):
    # Order 에서 추출되지 않는 변수 (`coupon_code`) 를 요구하는 템플릿 → missing_variables 발생 → 400.
    template = EmailNotificationTemplate.objects.create(
        code="coupon",
        title="쿠폰",
        sent_from="from@example.com",
        data='{"title":"쿠폰","from_":"f","send_to":"{{ customer_email }}","body":"{{ coupon_code }}"}',
        created_by=superuser,
        updated_by=superuser,
    )
    response = OrderNotificationsAdminApi(http_client=api_client).send(
        {"channel": "email", "template_id": str(template.id)}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "missing_context_variables" in str(response.json())
