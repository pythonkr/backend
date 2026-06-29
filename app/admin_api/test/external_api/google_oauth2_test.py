import http
from unittest.mock import patch

import pytest
from django.urls import reverse
from external_api.google_oauth2.models import GoogleOAuth2
from httpx import HTTPError
from rest_framework.test import APIClient

SERIALIZER_PATH = "admin_api.serializers.external_api.google_oauth2"


@pytest.fixture
def google_oauth_record(db):
    return GoogleOAuth2.objects.create(refresh_token="rt-test")  # nosec: B106


# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected():
    response = APIClient().get(reverse("v1:admin-google-oauth2-list"))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


# ---- CRUD -------------------------------------------------------------------


@pytest.mark.django_db
def test_list_returns_active_records(api_client, google_oauth_record):
    response = api_client.get(reverse("v1:admin-google-oauth2-list"))
    assert response.status_code == http.HTTPStatus.OK
    ids = [row["id"] for row in response.json()["results"]]
    assert str(google_oauth_record.id) in ids


@pytest.mark.django_db
def test_list_excludes_soft_deleted(api_client, google_oauth_record):
    GoogleOAuth2.objects.filter(id=google_oauth_record.id).delete()
    response = api_client.get(reverse("v1:admin-google-oauth2-list"))
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()["results"] == []


@pytest.mark.django_db
def test_retrieve_includes_refresh_token(api_client, google_oauth_record):
    response = api_client.get(reverse("v1:admin-google-oauth2-detail", kwargs={"pk": google_oauth_record.id}))
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()["refresh_token"] == google_oauth_record.refresh_token


@pytest.mark.django_db
def test_create_with_refresh_token(api_client):
    with patch(f"{SERIALIZER_PATH}.fetch_access_token", return_value={"access_token": "tok"}):
        response = api_client.post(
            reverse("v1:admin-google-oauth2-list"),
            data={"refresh_token": "rt-new"},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.CREATED
    assert GoogleOAuth2.objects.filter(refresh_token="rt-new").exists()  # nosec: B106


@pytest.mark.django_db
def test_create_rejects_invalid_refresh_token(api_client):
    with patch(f"{SERIALIZER_PATH}.fetch_access_token", side_effect=HTTPError("invalid_grant")):
        response = api_client.post(
            reverse("v1:admin-google-oauth2-list"),
            data={"refresh_token": "rt-bad"},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert not GoogleOAuth2.objects.filter(refresh_token="rt-bad").exists()  # nosec: B106


@pytest.mark.django_db
def test_partial_update_changes_refresh_token(api_client, google_oauth_record):
    with patch(f"{SERIALIZER_PATH}.fetch_access_token", return_value={"access_token": "tok"}):
        response = api_client.patch(
            reverse("v1:admin-google-oauth2-detail", kwargs={"pk": google_oauth_record.id}),
            data={"refresh_token": "rt-updated"},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.OK
    google_oauth_record.refresh_from_db()
    assert google_oauth_record.refresh_token == "rt-updated"  # nosec: B105


@pytest.mark.django_db
def test_partial_update_skips_validation_when_refresh_token_unchanged(api_client, google_oauth_record):
    with patch(f"{SERIALIZER_PATH}.fetch_access_token") as mock_fetch:
        response = api_client.patch(
            reverse("v1:admin-google-oauth2-detail", kwargs={"pk": google_oauth_record.id}),
            data={"refresh_token": google_oauth_record.refresh_token},
            format="json",
        )
    assert response.status_code == http.HTTPStatus.OK
    mock_fetch.assert_not_called()


@pytest.mark.django_db
def test_destroy_soft_deletes(api_client, google_oauth_record):
    response = api_client.delete(reverse("v1:admin-google-oauth2-detail", kwargs={"pk": google_oauth_record.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    google_oauth_record.refresh_from_db()
    assert google_oauth_record.deleted_at is not None


@pytest.mark.django_db
def test_put_is_405(api_client, google_oauth_record):
    response = api_client.put(
        reverse("v1:admin-google-oauth2-detail", kwargs={"pk": google_oauth_record.id}),
        data={"refresh_token": "rt-x"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED


# ---- access-token action ----------------------------------------------------


@pytest.mark.django_db
def test_access_token_returns_full_info_on_success(api_client, google_oauth_record):
    with (
        patch(
            f"{SERIALIZER_PATH}.fetch_access_token",
            return_value={
                "access_token": "ya29.x",
                "token_type": "Bearer",
                "expires_in": 3599,
                "scope": "https://x https://y",
            },
        ),
        patch(
            f"{SERIALIZER_PATH}.fetch_token_info",
            return_value={
                "expires_in": "3500",
                "email": "foo@bar",
                "aud": "client-id",
                "scope": "https://x https://y",
            },
        ),
    ):
        response = api_client.post(
            reverse("v1:admin-google-oauth2-issue-access-token", kwargs={"pk": google_oauth_record.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert body == {
        "is_valid": True,
        "access_token": "ya29.x",
        "token_type": "Bearer",
        "expires_in": 3500,
        "scopes": ["https://x", "https://y"],
        "email": "foo@bar",
        "audience": "client-id",
        "error": None,
    }


@pytest.mark.django_db
def test_access_token_falls_back_to_token_payload_when_tokeninfo_fails(api_client, google_oauth_record):
    with (
        patch(
            f"{SERIALIZER_PATH}.fetch_access_token",
            return_value={
                "access_token": "ya29.x",
                "token_type": "Bearer",
                "expires_in": 3599,
                "scope": "https://x",
            },
        ),
        patch(f"{SERIALIZER_PATH}.fetch_token_info", side_effect=HTTPError("boom")),
    ):
        response = api_client.post(
            reverse("v1:admin-google-oauth2-issue-access-token", kwargs={"pk": google_oauth_record.id})
        )
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert body["is_valid"] is True
    assert body["access_token"] == "ya29.x"
    assert body["expires_in"] == 3599
    assert body["scopes"] == ["https://x"]
    assert body["email"] is None
    assert body["audience"] is None


@pytest.mark.django_db
def test_access_token_returns_502_when_refresh_fails(api_client, google_oauth_record):
    with patch(f"{SERIALIZER_PATH}.fetch_access_token", side_effect=HTTPError("invalid_grant")):
        response = api_client.post(
            reverse("v1:admin-google-oauth2-issue-access-token", kwargs={"pk": google_oauth_record.id})
        )
    assert response.status_code == http.HTTPStatus.BAD_GATEWAY
    assert "invalid_grant" in response.json()["detail"]


@pytest.mark.django_db
def test_access_token_calls_google_with_record_refresh_token(api_client, google_oauth_record):
    with (
        patch(
            f"{SERIALIZER_PATH}.fetch_access_token",
            return_value={"access_token": "tok", "scope": ""},
        ) as mock_fetch,
        patch(f"{SERIALIZER_PATH}.fetch_token_info", return_value={}),
    ):
        api_client.post(reverse("v1:admin-google-oauth2-issue-access-token", kwargs={"pk": google_oauth_record.id}))
    mock_fetch.assert_called_once_with(google_oauth_record.refresh_token)
