import logging
import types
from unittest.mock import patch

import pytest
from core.models import BaseAbstractModelQuerySet
from notification.models import (
    EmailNotificationHistory,
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationHistory,
    NHNCloudKakaoAlimTalkNotificationTemplate,
)
from notification.models.base import NotificationStatus
from shop.order.models import CustomerInfo, Order
from shop.payment_history.tasks import send_payment_completed_notifications
from user.models import UserExt

_EMAIL_TEMPLATE_CODE = "payment_completed_email"
_ALIMTALK_TEMPLATE_CODE = "payment_completed_alimtalk"

_EMAIL_LOGGER = "shop.payment_history.tasks"
_SLACK_LOGGER = "slack_logger"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db):
    return UserExt.objects.create_user(username="buyer", email="buyer@example.com", password="x")  # nosec B106


@pytest.fixture
def order(user):
    return Order.objects.create(user=user, name="파이콘 한국 2026 티켓")


@pytest.fixture
def order_with_customer(order):
    CustomerInfo.objects.create(
        order=order,
        name="홍길동",
        phone="01012345678",
        email="customer@example.com",
    )
    return order


@pytest.fixture
def email_template(db):
    return EmailNotificationTemplate.objects.create(
        code=_EMAIL_TEMPLATE_CODE,
        title="결제 완료 이메일",
        sent_from="noreply@pycon.kr",
        data=(
            '{"title":"결제가 완료되었습니다",'
            '"body":"{{ order_name }} - 안녕하세요 {{ customer_name }}님,'
            ' {{ customer_phone }}, {{ customer_email }}"}'
        ),
    )


@pytest.fixture
def alimtalk_template(db):
    # 알림톡 템플릿은 NHN Cloud 동기화 전용이라 .create()가 차단됨 — bulk_create로 우회.
    template = NHNCloudKakaoAlimTalkNotificationTemplate(
        code=_ALIMTALK_TEMPLATE_CODE,
        title="결제 완료 알림톡",
        sent_from="sender_key_abc",
        data='{"templateContent":"안녕하세요 #{name}님","buttons":[]}',
    )
    [created] = BaseAbstractModelQuerySet(model=NHNCloudKakaoAlimTalkNotificationTemplate).bulk_create([template])
    return created


@pytest.fixture
def override_email_setting(settings):
    settings.NOTIFICATION = types.SimpleNamespace(
        payment_completed_alimtalk_template_code=_ALIMTALK_TEMPLATE_CODE,
        payment_completed_email_template_code=_EMAIL_TEMPLATE_CODE,
    )


@pytest.fixture
def override_email_setting_with_error(settings):
    settings.NOTIFICATION = types.SimpleNamespace(
        payment_completed_alimtalk_template_code="", payment_completed_email_template_code="nonexistent"
    )


# ---------------------------------------------------------------------------
# Happy path — 이메일
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_creates_email_history_when_template_exists(order_with_customer, email_template, override_email_setting):
    send_payment_completed_notifications(str(order_with_customer.id))

    history = EmailNotificationHistory.objects.filter_active().get()
    sent_to = history.sent_to_list.get()
    assert sent_to.recipient == "customer@example.com"
    assert sent_to.context == {
        "order_name": "파이콘 한국 2026 티켓",
        "first_paid_at": None,
        "first_paid_price": 0,
        "customer_name": "홍길동",
        "customer_phone": "01012345678",
        "customer_email": "customer@example.com",
    }
    assert sent_to.status == NotificationStatus.CREATED


# ---------------------------------------------------------------------------
# Happy path — 알림톡
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_creates_alimtalk_history_when_template_exists(order_with_customer, alimtalk_template, override_email_setting):
    send_payment_completed_notifications(str(order_with_customer.id))

    history = NHNCloudKakaoAlimTalkNotificationHistory.objects.filter_active().get()
    sent_to = history.sent_to_list.get()
    assert sent_to.recipient == "01012345678"
    assert sent_to.status == NotificationStatus.CREATED


# ---------------------------------------------------------------------------
# 주문 / customer_info 누락
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_logs_error_and_creates_no_history_when_order_not_found(caplog):
    with caplog.at_level(logging.ERROR, logger=_SLACK_LOGGER):
        send_payment_completed_notifications("00000000-0000-0000-0000-000000000000")

    assert any("주문을 찾을 수 없습니다" in r.getMessage() for r in caplog.records)
    assert EmailNotificationHistory.objects.count() == 0
    assert NHNCloudKakaoAlimTalkNotificationHistory.objects.count() == 0


@pytest.mark.django_db
def test_logs_error_and_creates_no_history_when_customer_info_missing(order, caplog):
    with caplog.at_level(logging.ERROR, logger=_SLACK_LOGGER):
        send_payment_completed_notifications(str(order.id))

    assert any("customer_info가 없는" in r.getMessage() for r in caplog.records)
    assert EmailNotificationHistory.objects.count() == 0
    assert NHNCloudKakaoAlimTalkNotificationHistory.objects.count() == 0


# ---------------------------------------------------------------------------
# 템플릿 누락
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_logs_warning_and_creates_no_history_when_email_template_not_found(
    order_with_customer, caplog, override_email_setting_with_error
):
    with caplog.at_level(logging.WARNING, logger=_EMAIL_LOGGER):
        send_payment_completed_notifications(str(order_with_customer.id))

    assert any("이메일 발송 건너뜀" in r.getMessage() for r in caplog.records)
    assert EmailNotificationHistory.objects.count() == 0


@pytest.mark.django_db
def test_logs_error_and_creates_no_history_when_alimtalk_template_not_found(
    order_with_customer, caplog, override_email_setting_with_error
):
    with caplog.at_level(logging.ERROR, logger=_SLACK_LOGGER):
        send_payment_completed_notifications(str(order_with_customer.id))

    assert any("알림톡 발송 실패" in r.getMessage() for r in caplog.records)
    assert NHNCloudKakaoAlimTalkNotificationHistory.objects.count() == 0


# ---------------------------------------------------------------------------
# 채널 독립성 — 한 채널 실패가 다른 채널을 막지 않아야 함
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_alimtalk_failure_does_not_prevent_email(
    order_with_customer, email_template, alimtalk_template, override_email_setting
):
    with patch(
        "notification.models.NHNCloudKakaoAlimTalkNotificationHistory.objects.create_for_recipients",
        side_effect=Exception("alimtalk boom"),
    ):
        send_payment_completed_notifications(str(order_with_customer.id))

    assert EmailNotificationHistory.objects.filter_active().count() == 1


@pytest.mark.django_db
def test_email_failure_does_not_prevent_alimtalk(
    order_with_customer, email_template, alimtalk_template, override_email_setting
):
    with patch(
        "notification.models.EmailNotificationHistory.objects.create_for_recipients",
        side_effect=Exception("email boom"),
    ):
        send_payment_completed_notifications(str(order_with_customer.id))

    assert NHNCloudKakaoAlimTalkNotificationHistory.objects.filter_active().count() == 1
