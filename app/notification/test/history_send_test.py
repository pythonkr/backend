import logging
from unittest.mock import patch

import pytest
from notification.models import EmailNotificationHistory, EmailNotificationTemplate
from notification.models.base import NotificationStatus
from user.models import UserExt


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


@pytest.fixture
def email_template(system_user):
    return EmailNotificationTemplate.objects.create(
        code="c",
        title="t",
        from_address="from@example.com",
        data='{"title":"hi","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )


@pytest.mark.django_db
def test_history_initial_status_is_created(email_template):
    history = email_template.histories.create(send_to="to@example.com", context={})
    assert history.status == NotificationStatus.CREATED


@pytest.mark.django_db
def test_history_success_transitions_to_sent(email_template):
    history = email_template.histories.create(send_to="to@example.com", context={})
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        history.send()
        mock_client.send_message.assert_called_once()
    history.refresh_from_db()
    assert history.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_history_failure_transitions_to_failed_and_propagates(email_template):
    history = email_template.histories.create(send_to="to@example.com", context={})
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            history.send()
    history.refresh_from_db()
    assert history.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_history_failure_logs_to_slack_logger(email_template, caplog):
    history = email_template.histories.create(send_to="bad@example.com", context={})
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("api down")
        with caplog.at_level(logging.ERROR, logger="slack_logger"):
            with pytest.raises(RuntimeError):
                history.send()
    # slack_logger에 ERROR 레벨로 기록되고, exc_info가 첨부되어야 함
    records = [r for r in caplog.records if r.name == "slack_logger"]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
    assert "send_to=bad@example.com" in records[0].getMessage()


@pytest.mark.django_db
def test_history_send_parameters_uses_rendered_payload(system_user):
    # build_send_parameters가 template.render(context)를 통과시키는지 확인
    tpl = EmailNotificationTemplate.objects.create(
        code="render",
        title="t",
        from_address="a@b.c",
        data='{"title":"안녕 {{ name }}","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )
    history = tpl.histories.create(send_to="to@example.com", context={"name": "길동"})
    params = history.build_send_parameters()
    assert params["payload"]["title"] == "안녕 길동"
    assert params["send_to"] == "to@example.com"
    assert params["sent_from"] == "a@b.c"
    assert params["template_code"] == "render"


@pytest.mark.django_db
def test_history_template_code_property_returns_template_code(email_template):
    history = email_template.histories.create(send_to="to@example.com", context={})
    assert history.template_code == email_template.code


@pytest.mark.django_db
def test_history_send_fails_fast_when_context_missing_template_variables(system_user):
    # 발송 시 context에 누락된 템플릿 변수가 있으면 RANDOM 텍스트로 채워 보내는 게 아니라 즉시 실패해야 함.
    tpl = EmailNotificationTemplate.objects.create(
        code="missing-var",
        title="t",
        from_address="a@b.c",
        data='{"title":"안녕 {{ name }}님","from_":"f","send_to":"r","body":"{{ message }}"}',
        created_by=system_user,
        updated_by=system_user,
    )
    history = tpl.histories.create(send_to="to@example.com", context={"name": "길동"})
    with pytest.raises(ValueError, match="message"):
        history.send()
    history.refresh_from_db()
    assert history.status == NotificationStatus.FAILED
