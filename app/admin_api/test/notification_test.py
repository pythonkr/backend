import http
from unittest.mock import patch

import pytest
from django.urls import reverse
from notification.models import EmailNotificationTemplate
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
            "from_address": "from@example.com",
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
        code="welcome", title="A", from_address="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    EmailNotificationTemplate.objects.create(
        code="goodbye", title="B", from_address="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )

    response = api_client.get(reverse("v1:admin-notification-email-template-list"), {"code": "welc"})
    assert response.status_code == http.HTTPStatus.OK
    codes = [row["code"] for row in response.json()]
    assert codes == ["welcome"]


@pytest.mark.django_db
def test_template_list_filter_by_title(api_client, superuser):
    EmailNotificationTemplate.objects.create(
        code="t1", title="환영합니다", from_address="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    EmailNotificationTemplate.objects.create(
        code="t2", title="안녕히가세요", from_address="a@x.com", data="{}", created_by=superuser, updated_by=superuser
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
    # context를 비워도 missing variable에 대해 RANDOM placeholder로 채워서 항상 렌더 가능해야 함.
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
    # Kakao는 ReadOnlyModelViewSet — collection POST(create) 미지원
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


# ---- create_history (POST /template/{id}/history/) --------------------------


@pytest.mark.django_db
def test_create_history_creates_row_and_marks_sent_on_success(api_client, sms_template):
    with patch("notification.models.nhn_cloud_sms.NHNCloudSMSNotificationHistory.client"):
        response = api_client.post(
            reverse("v1:admin-notification-sms-template-create-history", kwargs={"pk": sms_template.id}),
            data={"send_to": "01012345678", "context": {"name": "길동"}},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    body = response.json()
    assert body["status"] == NotificationStatus.SENT
    assert body["send_to"] == "01012345678"


@pytest.mark.django_db
def test_create_history_marks_failed_when_send_raises(api_client, sms_template):
    # 외부 발송이 실패해도 응답은 201이고, status가 FAILED로 영속화되어 있어야 함.
    with patch("notification.models.nhn_cloud_sms.NHNCloudSMSNotificationHistory.client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("external api down")
        response = api_client.post(
            reverse("v1:admin-notification-sms-template-create-history", kwargs={"pk": sms_template.id}),
            data={"send_to": "01012345678", "context": {"name": "길동"}},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    assert response.json()["status"] == NotificationStatus.FAILED


# ---- History List / Retrieve / Filter ---------------------------------------


@pytest.fixture
def email_history(email_template):
    return email_template.histories.create(send_to="to@example.com", context={"name": "길동", "recipient": "x"})


@pytest.mark.django_db
def test_history_list_returns_rows(api_client, email_history):
    response = api_client.get(reverse("v1:admin-notification-email-history-list"))
    assert response.status_code == http.HTTPStatus.OK
    ids = [row["id"] for row in response.json()]
    assert str(email_history.id) in ids


@pytest.mark.django_db
def test_history_list_filter_by_template(api_client, email_template, superuser):
    other_template = EmailNotificationTemplate.objects.create(
        code="other", title="X", from_address="a@x.com", data="{}", created_by=superuser, updated_by=superuser
    )
    matching = email_template.histories.create(send_to="t@x", context={})
    other_template.histories.create(send_to="t@x", context={})

    response = api_client.get(reverse("v1:admin-notification-email-history-list"), {"template": str(email_template.id)})
    assert response.status_code == http.HTTPStatus.OK
    ids = [row["id"] for row in response.json()]
    assert ids == [str(matching.id)]


@pytest.mark.django_db
def test_history_list_filter_by_created_by_username(api_client, email_template, superuser):
    # API 경로로 history를 만들어야 BaseAbstractModelQuerySet.create()의 get_current_user()가
    # 인증된 superuser를 created_by로 잡음 (fixture에서 직접 .create()하면 thread_local이 비어있음).
    with patch("notification.models.email.EmailNotificationHistory.client"):
        api_client.post(
            reverse("v1:admin-notification-email-template-create-history", kwargs={"pk": email_template.id}),
            data={"send_to": "to@example.com", "context": {"name": "x", "recipient": "y"}},
            format="json",
        )

    response = api_client.get(
        reverse("v1:admin-notification-email-history-list"), {"created_by__username": superuser.username}
    )
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) == 1


# ---- History PATCH (SENDING → FAILED 만 허용) -------------------------------


@pytest.mark.django_db
def test_history_patch_allows_sending_to_failed(api_client, email_history):
    email_history.status = NotificationStatus.SENDING
    email_history.save(update_fields=["status"])

    response = api_client.patch(
        reverse("v1:admin-notification-email-history-detail", kwargs={"pk": email_history.id}),
        data={"status": NotificationStatus.FAILED},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK
    email_history.refresh_from_db()
    assert email_history.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_history_patch_rejects_other_transitions(api_client, email_history):
    # CREATED → FAILED 같은 임의 전이는 거부되어야 함.
    response = api_client.patch(
        reverse("v1:admin-notification-email-history-detail", kwargs={"pk": email_history.id}),
        data={"status": NotificationStatus.FAILED},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_history_patch_rejects_sending_to_sent(api_client, email_history):
    email_history.status = NotificationStatus.SENDING
    email_history.save(update_fields=["status"])
    response = api_client.patch(
        reverse("v1:admin-notification-email-history-detail", kwargs={"pk": email_history.id}),
        data={"status": NotificationStatus.SENT},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- History Retry ----------------------------------------------------------


@pytest.mark.django_db
def test_retry_succeeds_on_failed_history(api_client, email_history):
    email_history.status = NotificationStatus.FAILED
    email_history.save(update_fields=["status"])

    with patch("notification.models.email.EmailNotificationHistory.client"):
        response = api_client.post(
            reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    email_history.refresh_from_db()
    assert email_history.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_retry_keeps_status_failed_when_send_raises(api_client, email_history):
    email_history.status = NotificationStatus.FAILED
    email_history.save(update_fields=["status"])

    with patch("notification.models.email.EmailNotificationHistory.client") as mock_client:
        mock_client.send_message.side_effect = RuntimeError("still down")
        response = api_client.post(
            reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    email_history.refresh_from_db()
    assert email_history.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_retry_rejects_non_failed_history(api_client, email_history):
    # 기본 상태(CREATED)는 retry 대상이 아님.
    response = api_client.post(reverse("v1:admin-notification-email-history-retry", kwargs={"pk": email_history.id}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- 채널 간 격리 -----------------------------------------------------------


@pytest.mark.django_db
def test_email_history_endpoint_does_not_return_sms_histories(api_client, sms_template):
    sms_template.histories.create(send_to="01012345678", context={"name": "길동"})

    response = api_client.get(reverse("v1:admin-notification-email-history-list"))
    assert response.status_code == http.HTTPStatus.OK
    assert response.json() == []
    response = api_client.get(reverse("v1:admin-notification-sms-history-list"))
    assert len(response.json()) == 1
