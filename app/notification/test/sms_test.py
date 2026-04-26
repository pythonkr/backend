from unittest.mock import patch

import pytest
from notification.models import NHNCloudSMSNotificationHistory, NHNCloudSMSNotificationTemplate
from notification.models.base import NotificationStatus, UnhandledVariableHandling
from user.models import UserExt


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


# 인메모리 인스턴스 — 순수 render/preview 검증은 DB 영속화가 필요하지 않음.
@pytest.fixture
def sms_template_in_memory():
    return NHNCloudSMSNotificationTemplate(
        code="welcome-sms",
        title="Welcome SMS",
        from_no="0212345678",
        data='{"body":"안녕하세요 {{ name }}님"}',
    )


@pytest.fixture
def mms_template_in_memory():
    return NHNCloudSMSNotificationTemplate(
        code="welcome-mms",
        title="Welcome MMS",
        from_no="0212345678",
        data='{"title":"공지 {{ event }}","body":"안녕하세요 {{ name }}님"}',
    )


@pytest.fixture
def sms_template_persisted(system_user):
    return NHNCloudSMSNotificationTemplate.objects.create(
        code="welcome-sms",
        title="Welcome SMS",
        from_no="0212345678",
        data='{"body":"안녕하세요 {{ name }}님"}',
        created_by=system_user,
        updated_by=system_user,
    )


@pytest.fixture
def mms_template_persisted(system_user):
    return NHNCloudSMSNotificationTemplate.objects.create(
        code="welcome-mms",
        title="Welcome MMS",
        from_no="0212345678",
        data='{"title":"공지 {{ event }}","body":"안녕하세요 {{ name }}님"}',
        created_by=system_user,
        updated_by=system_user,
    )


# ---- 템플릿 render() --------------------------------------------------------


def test_sms_short_render_returns_body_only(sms_template_in_memory):
    result = sms_template_in_memory.render({"name": "길동"})
    assert result == {"body": "안녕하세요 길동님"}


def test_sms_long_mms_render_includes_title(mms_template_in_memory):
    result = mms_template_in_memory.render({"event": "PyCon", "name": "길동"})
    assert result == {"title": "공지 PyCon", "body": "안녕하세요 길동님"}


def test_sms_render_does_not_raise_when_title_empty_but_body_present():
    # title이 빈 문자열이어도 body만 있으면 단문 SMS로 발송 가능
    tpl = NHNCloudSMSNotificationTemplate(data='{"title":"{{ subj }}","body":"hello"}')
    result = tpl.render({}, UnhandledVariableHandling.REMOVE)
    assert result["body"] == "hello"
    assert result["title"] == ""


# ---- 미리보기 HTML ----------------------------------------------------------


def test_sms_preview_short_renders_body(sms_template_in_memory):
    html = sms_template_in_memory.render_as_html({"name": "길동"})
    assert html.strip().startswith("<html")
    assert "안녕하세요 길동님" in html


def test_sms_preview_long_mms_renders_title_block(mms_template_in_memory):
    html = mms_template_in_memory.render_as_html({"event": "PyCon", "name": "길동"})
    # MMS는 `title`이 있을 때만 toast-sms-title 블록을 렌더
    assert 'class="toast-sms-title"' in html
    assert "공지 PyCon" in html


def test_sms_preview_short_omits_title_block(sms_template_in_memory):
    html = sms_template_in_memory.render_as_html({"name": "길동"})
    assert 'class="toast-sms-title"' not in html


# ---- History.build_send_parameters() ----------------------------------------


@pytest.mark.django_db
def test_sms_history_short_payload_excludes_title(sms_template_persisted):
    history = sms_template_persisted.histories.create(send_to="01012345678", context={"name": "길동"})
    params = history.build_send_parameters()

    assert params["send_to"] == "01012345678"
    assert params["sent_from"] == "0212345678"
    assert params["template_code"] == "welcome-sms"
    assert params["payload"] == {"body": "안녕하세요 길동님"}


@pytest.mark.django_db
def test_sms_history_long_mms_payload_includes_title(mms_template_persisted):
    history = mms_template_persisted.histories.create(
        send_to="01012345678",
        context={"event": "PyCon", "name": "길동"},
    )
    params = history.build_send_parameters()

    assert params["payload"] == {"title": "공지 PyCon", "body": "안녕하세요 길동님"}


# ---- History.send() 상태 전이 -----------------------------------------------


@pytest.mark.django_db
def test_sms_history_send_success_transitions_to_sent(sms_template_persisted):
    history = sms_template_persisted.histories.create(send_to="01012345678", context={"name": "길동"})
    with patch.object(NHNCloudSMSNotificationHistory, "client") as mock_client:
        history.send()
        mock_client.send_message.assert_called_once()
    history.refresh_from_db()
    assert history.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_sms_history_send_failure_transitions_to_failed_and_propagates(sms_template_persisted):
    history = sms_template_persisted.histories.create(send_to="01012345678", context={"name": "길동"})
    with patch.object(NHNCloudSMSNotificationHistory, "client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            history.send()
    history.refresh_from_db()
    assert history.status == NotificationStatus.FAILED
