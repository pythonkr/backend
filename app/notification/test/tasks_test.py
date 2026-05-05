import logging
from unittest.mock import patch

import pytest
from notification.models import EmailNotificationHistory, EmailNotificationHistorySentTo, EmailNotificationTemplate
from notification.models.base import NotificationStatus
from notification.tasks import send_notification_to_recipient
from user.models import UserExt

LABEL = EmailNotificationHistorySentTo._meta.label_lower


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


@pytest.fixture
def email_template(system_user):
    return EmailNotificationTemplate.objects.create(
        code="t",
        title="t",
        sent_from="from@example.com",
        data='{"title":"hi","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )


@pytest.fixture
def sent_to(email_template):
    history = EmailNotificationHistory.objects.create_for_recipients(
        template=email_template,
        recipients=[{"recipient": "to@example.com"}],
    )
    return history.sent_to_list.get()


@pytest.mark.django_db
def test_task_sends_created_row(sent_to):
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        send_notification_to_recipient(LABEL, sent_to.id)
    mock_client.send_message.assert_called_once()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_task_resends_failed_row(sent_to):
    sent_to.status = NotificationStatus.FAILED
    sent_to.save(update_fields=["status"])
    with patch.object(EmailNotificationHistory, "client"):
        send_notification_to_recipient(LABEL, sent_to.id)
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_task_skips_sending_row_to_prevent_duplicate_send(sent_to):
    # 동시성/재배달 가드 — SENDING 중인 row를 다른 워커가 받아도 외부 호출이 일어나지 않아야 함.
    sent_to.status = NotificationStatus.SENDING
    sent_to.save(update_fields=["status"])
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        send_notification_to_recipient(LABEL, sent_to.id)
    mock_client.send_message.assert_not_called()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.SENDING


@pytest.mark.django_db
def test_task_skips_sent_row_to_prevent_duplicate_send(sent_to):
    sent_to.status = NotificationStatus.SENT
    sent_to.save(update_fields=["status"])
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        send_notification_to_recipient(LABEL, sent_to.id)
    mock_client.send_message.assert_not_called()


@pytest.mark.django_db
def test_task_marks_failed_and_propagates_external_failure(sent_to):
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("api down")
        with pytest.raises(RuntimeError, match="api down"):
            send_notification_to_recipient(LABEL, sent_to.id)
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_task_logs_unexpected_error_when_inner_save_fails(sent_to, caplog):
    # send() 내부 try가 못 잡는 경로(첫 status save 실패) — task가 "Batch send unexpected error"로 추가 로깅.
    with patch.object(EmailNotificationHistorySentTo, "save", side_effect=RuntimeError("db down")):
        with caplog.at_level(logging.ERROR, logger="slack_logger"):
            with pytest.raises(RuntimeError, match="db down"):
                send_notification_to_recipient(LABEL, sent_to.id)
    records = [r for r in caplog.records if "Batch send unexpected" in r.getMessage()]
    assert len(records) == 1
    assert records[0].exc_info is not None


@pytest.mark.django_db
def test_task_records_failure_reason_on_external_failure(sent_to):
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("boom-task")
        with pytest.raises(RuntimeError):
            send_notification_to_recipient(LABEL, sent_to.id)
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.FAILED
    assert sent_to.failure_reason is not None
    assert "boom-task" in sent_to.failure_reason


@pytest.mark.django_db
def test_task_records_failure_reason_when_inner_save_fails(sent_to):
    # send() 내부 save() 자체가 망가졌을 때, task의 outer fallback이 queryset.update()로
    # status=FAILED와 failure_reason을 기록해야 한다.
    with patch.object(EmailNotificationHistorySentTo, "save", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError, match="db down"):
            send_notification_to_recipient(LABEL, sent_to.id)
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.FAILED
    assert sent_to.failure_reason is not None
    assert "db down" in sent_to.failure_reason
