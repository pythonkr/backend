import http
from unittest.mock import patch

import pytest
from django.urls import reverse
from notification.models import (
    EmailNotificationHistory,
    EmailNotificationTemplate,
    NHNCloudSMSNotificationHistory,
)
from notification.models.base import NotificationStatus
from rest_framework.test import APIClient

# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected(email_template):
    response = APIClient().get(reverse("v1:admin-notification-email-template-list"))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


# ---- Template CRUD (Email) --------------------------------------------------


@pytest.mark.django_db
def test_template_list_returns_active_templates(api_client, email_template):
    response = api_client.get(reverse("v1:admin-notification-email-template-list"))
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert any(row["code"] == email_template.code for row in body)


@pytest.mark.django_db
def test_template_retrieve_includes_template_variables(api_client, email_template):
    response = api_client.get(reverse("v1:admin-notification-email-template-detail", kwargs={"pk": email_template.id}))
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert sorted(body["template_variables"]) == ["name", "recipient"]


@pytest.mark.django_db
def test_template_create(api_client):
    response = api_client.post(
        reverse("v1:admin-notification-email-template-list"),
        data={
            "code": "new-tpl",
            "title": "신규",
            "sent_from": "from@example.com",
            "data": '{"title":"x","from_":"f","send_to":"r","body":"b"}',
        },
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED
    assert EmailNotificationTemplate.objects.filter(code="new-tpl").exists()


@pytest.mark.django_db
def test_template_partial_update(api_client, email_template):
    response = api_client.patch(
        reverse("v1:admin-notification-email-template-detail", kwargs={"pk": email_template.id}),
        data={"title": "변경된 제목"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK
    email_template.refresh_from_db()
    assert email_template.title == "변경된 제목"


@pytest.mark.django_db
def test_template_destroy_soft_deletes(api_client, email_template):
    response = api_client.delete(
        reverse("v1:admin-notification-email-template-detail", kwargs={"pk": email_template.id})
    )
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    email_template.refresh_from_db()
    assert email_template.deleted_at is not None


# ---- Template Filters --------------------------------------------------------


@pytest.mark.django_db
def test_template_list_filter_by_code(api_client, superuser):
    EmailNotificationTemplate.objects.create(
        code="welcome", title="A", sent_from="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    EmailNotificationTemplate.objects.create(
        code="goodbye", title="B", sent_from="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )

    response = api_client.get(reverse("v1:admin-notification-email-template-list"), {"code": "welc"})
    assert response.status_code == http.HTTPStatus.OK
    codes = [row["code"] for row in response.json()]
    assert codes == ["welcome"]


@pytest.mark.django_db
def test_template_list_filter_by_title(api_client, superuser):
    EmailNotificationTemplate.objects.create(
        code="t1", title="환영합니다", sent_from="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    EmailNotificationTemplate.objects.create(
        code="t2", title="안녕히가세요", sent_from="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )

    response = api_client.get(reverse("v1:admin-notification-email-template-list"), {"title": "환영"})
    assert response.status_code == http.HTTPStatus.OK
    titles = [row["title"] for row in response.json()]
    assert titles == ["환영합니다"]


# ---- Render Preview ---------------------------------------------------------


@pytest.mark.django_db
def test_render_preview_returns_html_with_text_html_content_type(api_client, email_template):
    response = api_client.post(
        reverse("v1:admin-notification-email-template-render-preview", kwargs={"pk": email_template.id}),
        data={"context": {"name": "길동", "recipient": "to@example.com"}},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert body.lstrip().startswith("<html")
    assert "길동" in body


@pytest.mark.django_db
def test_render_preview_fills_missing_variables_with_random_placeholder(api_client, email_template):
    response = api_client.post(
        reverse("v1:admin-notification-email-template-render-preview", kwargs={"pk": email_template.id}),
        data={"context": {}},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK
    assert "RandomValue-" in response.content.decode()


@pytest.mark.django_db
def test_render_preview_works_for_kakao_template(api_client, kakao_template):
    response = api_client.post(
        reverse("v1:admin-notification-kakao-template-render-preview", kwargs={"pk": kakao_template.id}),
        data={"context": {"name": "길동"}},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK
    assert "길동" in response.content.decode()


# ---- Kakao 읽기 전용 ---------------------------------------------------------


@pytest.mark.django_db
def test_kakao_template_post_to_collection_is_405(api_client):
    response = api_client.post(reverse("v1:admin-notification-kakao-template-list"), data={}, format="json")
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_kakao_template_patch_is_405(api_client, kakao_template):
    response = api_client.patch(
        reverse("v1:admin-notification-kakao-template-detail", kwargs={"pk": kakao_template.id}),
        data={"title": "변경"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_kakao_template_delete_is_405(api_client, kakao_template):
    response = api_client.delete(
        reverse("v1:admin-notification-kakao-template-detail", kwargs={"pk": kakao_template.id})
    )
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED


# ---- History create (POST /history/) ----------------------------------------


@pytest.mark.django_db(transaction=True)
def test_create_history_via_template_creates_sent_to_and_sends(api_client, sms_template):
    with patch("notification.models.nhn_cloud_sms.NHNCloudSMSNotificationHistory.client"):
        response = api_client.post(
            reverse("v1:admin-notification-sms-history-list"),
            data={
                "template": str(sms_template.id),
                "sent_to_list": [{"recipient": "01012345678", "context": {"name": "길동"}}],
            },
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    body = response.json()
    assert body["template_code"] == sms_template.code
    assert body["sent_from"] == sms_template.sent_from
    assert body["sent_to_status_summary"]["sent"] == 1
    [sent_to] = body["sent_to_list"]
    assert sent_to["recipient"] == "01012345678"
    assert sent_to["status"] == NotificationStatus.SENT


@pytest.mark.django_db(transaction=True)
def test_create_history_marks_sent_to_failed_when_send_raises(api_client, sms_template):
    with patch("notification.models.nhn_cloud_sms.NHNCloudSMSNotificationHistory.client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("external api down")
        response = api_client.post(
            reverse("v1:admin-notification-sms-history-list"),
            data={
                "template": str(sms_template.id),
                "sent_to_list": [{"recipient": "01012345678", "context": {"name": "길동"}}],
            },
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    body = response.json()
    assert body["sent_to_status_summary"]["failed"] == 1
    assert body["sent_to_list"][0]["status"] == NotificationStatus.FAILED


@pytest.mark.django_db(transaction=True)
def test_create_history_with_multiple_recipients_and_per_recipient_context(api_client, sms_template):
    # 한 번의 요청으로 여러 수신자에게 서로 다른 context로 발송, 결과는 같은 history로 묶여 조회됨.
    with patch("notification.models.nhn_cloud_sms.NHNCloudSMSNotificationHistory.client") as mock_client:
        mock_client.send_message.side_effect = [None, RuntimeError("partial fail")]
        response = api_client.post(
            reverse("v1:admin-notification-sms-history-list"),
            data={
                "template": str(sms_template.id),
                "sent_to_list": [
                    {"recipient": "01000000001", "context": {"name": "A"}},
                    {"recipient": "01000000002", "context": {"name": "B"}},
                ],
            },
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    body = response.json()
    assert body["sent_to_status_summary"] == {"created": 0, "sending": 0, "sent": 1, "failed": 1}
    assert {s["recipient"] for s in body["sent_to_list"]} == {"01000000001", "01000000002"}


@pytest.mark.django_db(transaction=True)
def test_create_history_templateless_email(api_client):
    # 템플릿 없이 template_data + sent_from 직접 입력해 발송.
    with patch("notification.models.email.EmailNotificationHistory.client"):
        response = api_client.post(
            reverse("v1:admin-notification-email-history-list"),
            data={
                "template_data": '{"title":"hi {{ name }}","from_":"f","send_to":"r","body":"b"}',
                "sent_from": "from@example.com",
                "sent_to_list": [{"recipient": "to@example.com", "context": {"name": "길동"}}],
            },
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    body = response.json()
    assert body["template"] is None
    assert body["template_code"] == ""
    assert body["sent_from"] == "from@example.com"
    assert body["sent_to_status_summary"]["sent"] == 1


@pytest.mark.django_db
def test_create_history_kakao_requires_template(api_client):
    response = api_client.post(
        reverse("v1:admin-notification-kakao-history-list"),
        data={"sent_to_list": [{"recipient": "01012345678"}]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- History List / Retrieve / Filter ---------------------------------------


@pytest.fixture
def email_history(email_template):
    return EmailNotificationHistory.objects.create_for_recipients(
        template=email_template,
        recipients=[{"recipient": "to@example.com", "context": {"name": "길동", "recipient": "x"}}],
    )


@pytest.mark.django_db
def test_history_list_returns_rows(api_client, email_history):
    response = api_client.get(reverse("v1:admin-notification-email-history-list"))
    assert response.status_code == http.HTTPStatus.OK
    ids = [row["id"] for row in response.json()]
    assert str(email_history.id) in ids


@pytest.mark.django_db
def test_history_list_filter_by_template(api_client, email_template, superuser):
    other_template = EmailNotificationTemplate.objects.create(
        code="other", title="X", sent_from="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    matching = EmailNotificationHistory.objects.create_for_recipients(
        template=email_template, recipients=[{"recipient": "t@x"}]
    )
    EmailNotificationHistory.objects.create_for_recipients(template=other_template, recipients=[{"recipient": "t@x"}])

    response = api_client.get(reverse("v1:admin-notification-email-history-list"), {"template": str(email_template.id)})
    assert response.status_code == http.HTTPStatus.OK
    ids = [row["id"] for row in response.json()]
    assert ids == [str(matching.id)]


@pytest.mark.django_db(transaction=True)
def test_history_list_filter_by_created_by_username(api_client, email_template, superuser):
    # API 경로로 history를 만들어야 BaseAbstractModelQuerySet.create()의 get_current_user()가
    # 인증된 superuser를 created_by로 잡음.
    with patch("notification.models.email.EmailNotificationHistory.client"):
        api_client.post(
            reverse("v1:admin-notification-email-history-list"),
            data={
                "template": str(email_template.id),
                "sent_to_list": [{"recipient": "to@example.com", "context": {"name": "x", "recipient": "y"}}],
            },
            format="json",
        )

    response = api_client.get(
        reverse("v1:admin-notification-email-history-list"), {"created_by__username": superuser.username}
    )
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) == 1


# ---- History Retry ----------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_retry_resends_only_failed_sent_to(api_client, email_history):
    # 한 history 안에 SENT/FAILED가 섞여 있을 때 retry는 FAILED만 재시도.
    extra = EmailNotificationHistory.objects.create_for_recipients(
        template=email_history.template,
        recipients=[{"recipient": "extra@example.com"}],
    )
    # email_history의 sent_to 1개를 FAILED로, extra의 sent_to를 SENT로 설정 (격리 검증용)
    email_history.sent_to_list.update(status=NotificationStatus.FAILED)
    extra.sent_to_list.update(status=NotificationStatus.SENT)

    with patch("notification.models.email.EmailNotificationHistory.client") as mock_client:
        response = api_client.post(
            reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    assert mock_client.send_message.call_count == 1  # FAILED 1개만 재시도됨

    email_history.refresh_from_db()
    assert email_history.sent_to_list.get().status == NotificationStatus.SENT


@pytest.mark.django_db(transaction=True)
def test_retry_keeps_sent_to_failed_when_send_raises(api_client, email_history):
    email_history.sent_to_list.update(status=NotificationStatus.FAILED)

    with patch("notification.models.email.EmailNotificationHistory.client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("still down")
        response = api_client.post(
            reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    sent_to = email_history.sent_to_list.get()
    assert sent_to.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_retry_noop_when_no_failed_sent_to(api_client, email_history):
    # 기본 상태(CREATED)는 retry 대상이 아님 → 200 + 외부 호출 없음.
    with patch("notification.models.email.EmailNotificationHistory.client") as mock_client:
        response = api_client.post(
            reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    mock_client.send_message.assert_not_called()


# ---- 채널 간 격리 -----------------------------------------------------------


@pytest.mark.django_db
def test_email_history_endpoint_does_not_return_sms_histories(api_client, sms_template):
    NHNCloudSMSNotificationHistory.objects.create_for_recipients(
        template=sms_template,
        recipients=[{"recipient": "01012345678", "context": {"name": "길동"}}],
    )

    response = api_client.get(reverse("v1:admin-notification-email-history-list"))
    assert response.status_code == http.HTTPStatus.OK
    assert response.json() == []
    response = api_client.get(reverse("v1:admin-notification-sms-history-list"))
    assert len(response.json()) == 1
