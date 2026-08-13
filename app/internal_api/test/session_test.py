import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN, HTTP_405_METHOD_NOT_ALLOWED
from rest_framework.test import APIClient

SESSION_URL = reverse("v1:registration_desk:desk-session")
LOGIN_URL = reverse("headless:browser:account:login")


@pytest.mark.django_db
def test_session_rejects_anonymous(anon_client):
    assert anon_client.get(SESSION_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_session_rejects_non_superuser(customer_client):
    assert customer_client.get(SESSION_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_session_returns_staff_profile(staff_client, staff_user):
    staff_user.nickname = "등록데스크"
    staff_user.save()

    response = staff_client.get(SESSION_URL)

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "id": staff_user.id,
        "unique_id": str(staff_user.unique_id),
        "username": staff_user.username,
        "nickname": "등록데스크",
        "email": staff_user.email,
    }


@pytest.mark.django_db
def test_session_sets_csrf_cookie(staff_client, settings):
    assert settings.CSRF_COOKIE_NAME in staff_client.get(SESSION_URL).cookies


@pytest.mark.django_db
def test_session_sets_csrf_cookie_even_when_forbidden(anon_client, settings):
    # 로그인 직후 곧바로 PATCH 를 보낼 수 있어야 하므로 403 응답에도 쿠키를 실는다.
    assert settings.CSRF_COOKIE_NAME in anon_client.get(SESSION_URL).cookies


@pytest.mark.django_db
def test_session_does_not_handle_logout(staff_client):
    assert staff_client.delete(SESSION_URL).status_code == HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_email_password_login_creates_registration_desk_session(staff_user):
    staff_user.set_password("registration-desk-password")
    staff_user.save()
    client = APIClient(enforce_csrf_checks=True)
    csrf_response = client.get(SESSION_URL)
    csrf_token = csrf_response.cookies[settings.CSRF_COOKIE_NAME].value

    login_response = client.post(
        LOGIN_URL,
        {"email": staff_user.email, "password": "registration-desk-password"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert login_response.status_code == HTTP_200_OK
    assert client.get(SESSION_URL).status_code == HTTP_200_OK
