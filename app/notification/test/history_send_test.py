import logging
from unittest.mock import patch

import pytest
from notification.models import EmailNotificationHistory, EmailNotificationHistorySentTo, EmailNotificationTemplate
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
        sent_from="from@example.com",
        data='{"title":"hi","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )


def _create_history(template, recipient="to@example.com", context=None):
    return EmailNotificationHistory.objects.create_for_recipients(
        template=template,
        recipients=[{"recipient": recipient, "context": context or {}}],
    )


@pytest.mark.django_db
def test_sent_to_initial_status_is_created(email_template):
    history = _create_history(email_template)
    sent_to = history.sent_to_list.get()
    assert sent_to.status == NotificationStatus.CREATED


@pytest.mark.django_db
def test_sent_to_success_transitions_to_sent(email_template):
    history = _create_history(email_template)
    sent_to = history.sent_to_list.get()
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        sent_to.send()
        mock_client.send_message.assert_called_once()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_sent_to_failure_transitions_to_failed_and_propagates(email_template):
    history = _create_history(email_template)
    sent_to = history.sent_to_list.get()
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            sent_to.send()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_sent_to_failure_records_traceback_in_failure_reason(email_template):
    history = _create_history(email_template)
    sent_to = history.sent_to_list.get()
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("kaboom-xyz")
        with pytest.raises(RuntimeError):
            sent_to.send()
    sent_to.refresh_from_db()
    assert sent_to.failure_reason is not None
    assert "RuntimeError" in sent_to.failure_reason
    assert "kaboom-xyz" in sent_to.failure_reason
    assert "Traceback" in sent_to.failure_reason


@pytest.mark.django_db
def test_sent_to_retry_clears_previous_failure_reason(email_template):
    history = _create_history(email_template)
    sent_to = history.sent_to_list.get()
    sent_to.status = NotificationStatus.FAILED
    sent_to.failure_reason = "previous failure"
    sent_to.save(update_fields=["status", "failure_reason"])

    with patch.object(EmailNotificationHistory, "client"):
        sent_to.send()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.SENT
    assert sent_to.failure_reason is None


@pytest.mark.django_db
def test_sent_to_failure_logs_to_slack_logger(email_template, caplog):
    history = _create_history(email_template, recipient="bad@example.com")
    sent_to = history.sent_to_list.get()
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("api down")
        with caplog.at_level(logging.ERROR, logger="slack_logger"):
            with pytest.raises(RuntimeError):
                sent_to.send()
    records = [r for r in caplog.records if r.name == "slack_logger"]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
    assert "recipient=bad@example.com" in records[0].getMessage()


@pytest.mark.django_db
def test_history_send_parameters_uses_rendered_payload(system_user):
    tpl = EmailNotificationTemplate.objects.create(
        code="render",
        title="t",
        sent_from="a@b.c",
        data='{"title":"안녕 {{ name }}","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )
    history = _create_history(tpl, recipient="to@example.com", context={"name": "길동"})
    sent_to = history.sent_to_list.get()
    params = sent_to.build_send_parameters()
    assert params["payload"]["title"] == "안녕 길동"
    assert params["send_to"] == "to@example.com"
    assert params["sent_from"] == "a@b.c"
    assert params["template_code"] == "render"


@pytest.mark.django_db
def test_email_payload_body_is_html_rendered(system_user):
    # 이메일 발송 시 payload["body"]는 HTML 템플릿으로 렌더링된 결과여야 함.
    tpl = EmailNotificationTemplate.objects.create(
        code="html-body",
        title="t",
        sent_from="a@b.c",
        data='{"title":"안녕 {{ name }}","body":"본문 {{ name }}"}',
        created_by=system_user,
        updated_by=system_user,
    )
    history = _create_history(tpl, context={"name": "길동"})
    sent_to = history.sent_to_list.get()
    payload = sent_to.payload

    # title은 plain text
    assert payload["title"] == "안녕 길동"
    assert not payload["title"].strip().startswith("<")

    # body는 HTML 렌더링 결과
    assert payload["body"].strip().startswith("<")
    assert "길동" in payload["body"]


@pytest.mark.django_db
def test_history_template_code_property_returns_template_code(email_template):
    history = _create_history(email_template)
    assert history.template_code == email_template.code


@pytest.mark.django_db
def test_send_fails_fast_when_context_missing_template_variables(system_user):
    # 발송 시 sent_to.context에 누락된 템플릿 변수가 있으면 즉시 실패해야 함.
    tpl = EmailNotificationTemplate.objects.create(
        code="missing-var",
        title="t",
        sent_from="a@b.c",
        data='{"title":"안녕 {{ name }}님","from_":"f","send_to":"r","body":"{{ message }}"}',
        created_by=system_user,
        updated_by=system_user,
    )
    history = _create_history(tpl, context={"name": "길동"})
    sent_to = history.sent_to_list.get()
    with pytest.raises(ValueError, match="message"):
        sent_to.send()
    sent_to.refresh_from_db()
    assert sent_to.status == NotificationStatus.FAILED


@pytest.mark.django_db(transaction=True)
def test_history_send_iterates_all_sent_to_and_swallows_individual_failures(system_user, email_template):
    history = EmailNotificationHistory.objects.create_for_recipients(
        template=email_template,
        recipients=[
            {"recipient": "ok1@example.com", "context": {}},
            {"recipient": "fail@example.com", "context": {}},
            {"recipient": "ok2@example.com", "context": {}},
        ],
    )
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = [None, RuntimeError("partial fail"), None]
        history.send()  # 개별 실패가 batch를 멈추지 않음

    by_recipient = {s.recipient: s for s in history.sent_to_list.all()}
    assert by_recipient["ok1@example.com"].status == NotificationStatus.SENT
    assert by_recipient["fail@example.com"].status == NotificationStatus.FAILED
    assert by_recipient["ok2@example.com"].status == NotificationStatus.SENT


@pytest.mark.django_db
def test_sent_to_status_summary_counts_by_status(email_template):
    history = EmailNotificationHistory.objects.create_for_recipients(
        template=email_template,
        recipients=[{"recipient": f"r{i}@example.com"} for i in range(3)],
    )
    sent_to_qs = history.sent_to_list.order_by("recipient")
    EmailNotificationHistorySentTo.objects.filter(id=sent_to_qs[0].id).update(status=NotificationStatus.SENT)
    EmailNotificationHistorySentTo.objects.filter(id=sent_to_qs[1].id).update(status=NotificationStatus.FAILED)
    # sent_to_qs[2] stays CREATED

    summary = history.sent_to_status_summary
    assert summary == {"created": 1, "sending": 0, "sent": 1, "failed": 1}


@pytest.mark.django_db(transaction=True)
def test_history_send_logs_unexpected_errors_outside_inner_try(email_template, caplog):
    # SentTo.send() 내부 try 밖에서 발생한 예외(예: status save 실패)는 inner catch+log에 안 잡힘 →
    # _send_each가 batch를 계속 진행하면서 상위에서 추가 로깅하는지 확인.
    history = _create_history(email_template)
    with patch.object(EmailNotificationHistorySentTo, "save", side_effect=RuntimeError("db down")):
        with caplog.at_level(logging.ERROR, logger="slack_logger"):
            history.send()  # propagate 안 됨

    records = [r for r in caplog.records if "Batch send unexpected" in r.getMessage()]
    assert len(records) == 1
    assert records[0].exc_info is not None


@pytest.mark.django_db(transaction=True)
def test_history_retry_skips_non_matching_status(email_template):
    # statuses에 포함되지 않는 status의 sent_to는 재시도 대상에서 제외 — 외부 호출이 발생하지 않음.
    history = _create_history(email_template)  # 기본 status는 CREATED.
    with patch.object(EmailNotificationHistory, "client") as mock_client:
        history.retry(statuses=[NotificationStatus.FAILED])
    mock_client.send_message.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_history_retry_resends_matching_status(email_template):
    history = _create_history(email_template)
    history.sent_to_list.update(status=NotificationStatus.FAILED)

    with patch.object(EmailNotificationHistory, "client"):
        history.retry(statuses=[NotificationStatus.FAILED])
    sent_to = history.sent_to_list.get()
    assert sent_to.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_create_for_recipients_snapshots_template_data_and_sent_from(email_template):
    # template snapshot — template이 이후 수정돼도 history는 그대로 유지.
    history = _create_history(email_template)
    assert history.template_data == email_template.data
    assert history.sent_from == email_template.sent_from

    email_template.data = '{"title":"NEW","from_":"f","send_to":"r","body":"b"}'
    email_template.save(update_fields=["data"])
    history.refresh_from_db()
    assert history.template_data != email_template.data  # snapshot은 그대로


@pytest.mark.django_db
def test_create_for_recipients_templateless_uses_transient_template(system_user):
    # template 없이 발송하려면 호출자가 unsaved EmailNotificationTemplate 인스턴스를 구성해 전달.
    with pytest.raises(ValueError, match="template"):
        EmailNotificationHistory.objects.create_for_recipients(
            template=EmailNotificationTemplate(),
            recipients=[{"recipient": "x@y.z"}],
        )

    history = EmailNotificationHistory.objects.create_for_recipients(
        template=EmailNotificationTemplate(
            data='{"title":"hi {{ name }}","from_":"f","send_to":"r","body":"b"}',
            sent_from="from@example.com",
        ),
        recipients=[{"recipient": "x@y.z", "context": {"name": "x"}}],
    )
    assert history.template_id is None
    assert history.template_code == ""
    assert history.sent_from == "from@example.com"
