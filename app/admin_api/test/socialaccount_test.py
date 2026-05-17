import http

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.urls import reverse
from rest_framework.test import APIClient
from user.models import UserExt

# ---- Fixtures ---------------------------------------------------------------


@pytest.fixture
def social_app(db) -> SocialApp:
    return SocialApp.objects.create(provider="google", name="Google", client_id="cid", secret="sec")  # nosec: B106


@pytest.fixture
def regular_user(db) -> UserExt:
    user = UserExt.objects.create_user(username="alice", email="alice@example.com", password="x")  # nosec: B106
    SocialAccount.objects.create(
        user=user, provider="google", uid="alice-google-1", extra_data={"email": "alice@example.com"}
    )
    EmailAddress.objects.create(user=user, email="alice@example.com", verified=True, primary=True)
    return user


@pytest.fixture
def multi_social_user(db) -> UserExt:
    user = UserExt.objects.create_user(username="bob", email="bob@example.com", password="x")  # nosec: B106
    SocialAccount.objects.create(user=user, provider="google", uid="bob-google-1", extra_data={})
    SocialAccount.objects.create(user=user, provider="kakao", uid="bob-kakao-1", extra_data={})
    EmailAddress.objects.create(user=user, email="bob@example.com", verified=True, primary=True)
    return user


# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_social_app_list_rejected():
    response = APIClient().get(reverse("v1:admin-social-app-list"))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


@pytest.mark.django_db
def test_non_superuser_social_app_list_rejected(regular_user):
    client = APIClient()
    client.force_authenticate(user=regular_user)
    response = client.get(reverse("v1:admin-social-app-list"))
    assert response.status_code == http.HTTPStatus.FORBIDDEN


@pytest.mark.django_db
def test_non_superuser_social_account_list_rejected(regular_user):
    client = APIClient()
    client.force_authenticate(user=regular_user)
    response = client.get(reverse("v1:admin-social-account-list"))
    assert response.status_code == http.HTTPStatus.FORBIDDEN


@pytest.mark.django_db
def test_non_superuser_email_address_list_rejected(regular_user):
    client = APIClient()
    client.force_authenticate(user=regular_user)
    response = client.get(reverse("v1:admin-email-address-list"))
    assert response.status_code == http.HTTPStatus.FORBIDDEN


# ---- SocialApp CRUD ---------------------------------------------------------


@pytest.mark.django_db
def test_social_app_list(api_client, social_app):
    response = api_client.get(reverse("v1:admin-social-app-list"))
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()
    assert any(row["id"] == social_app.id for row in rows)


@pytest.mark.django_db
def test_social_app_retrieve(api_client, social_app):
    response = api_client.get(reverse("v1:admin-social-app-detail", kwargs={"pk": social_app.id}))
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert body["provider"] == "google"
    # secret 은 마스킹 없이 평문 노출.
    assert body["secret"] == "sec"


@pytest.mark.django_db
def test_social_app_create(api_client):
    response = api_client.post(
        reverse("v1:admin-social-app-list"),
        data={
            "provider": "kakao",
            "name": "Kakao",
            "client_id": "kid",
            "secret": "ksec",
        },
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED, response.json()
    assert SocialApp.objects.filter(provider="kakao", name="Kakao").exists()


@pytest.mark.django_db
def test_social_app_partial_update(api_client, social_app):
    response = api_client.patch(
        reverse("v1:admin-social-app-detail", kwargs={"pk": social_app.id}),
        data={"name": "Google Renamed"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    social_app.refresh_from_db()
    assert social_app.name == "Google Renamed"


@pytest.mark.django_db
def test_social_app_destroy(api_client, social_app):
    response = api_client.delete(reverse("v1:admin-social-app-detail", kwargs={"pk": social_app.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    assert not SocialApp.objects.filter(pk=social_app.id).exists()


# ---- SocialAccount List / Retrieve / Destroy --------------------------------


@pytest.mark.django_db
def test_social_account_list_filter_by_user(api_client, regular_user, multi_social_user):
    response = api_client.get(reverse("v1:admin-social-account-list"), {"user": str(regular_user.id)})
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()
    assert {row["uid"] for row in rows} == {"alice-google-1"}


@pytest.mark.django_db
def test_social_account_no_create_endpoint(api_client, regular_user):
    response = api_client.post(
        reverse("v1:admin-social-account-list"),
        data={"user": regular_user.id, "provider": "naver", "uid": "x"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_social_account_destroy_with_multiple_socials_preserves_emails(api_client, multi_social_user):
    sa = SocialAccount.objects.get(user=multi_social_user, provider="google")
    response = api_client.delete(reverse("v1:admin-social-account-detail", kwargs={"pk": sa.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    # 다른 SA 남아있으므로 EA 는 보존.
    assert SocialAccount.objects.filter(user=multi_social_user).count() == 1
    assert EmailAddress.objects.filter(user=multi_social_user).count() == 1


@pytest.mark.django_db
def test_social_account_destroy_last_social_cascades_to_emails(api_client, regular_user):
    sa = SocialAccount.objects.get(user=regular_user)
    response = api_client.delete(reverse("v1:admin-social-account-detail", kwargs={"pk": sa.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    # 마지막 SA 였으므로 같은 user 의 EA 모두 삭제.
    assert SocialAccount.objects.filter(user=regular_user).count() == 0
    assert EmailAddress.objects.filter(user=regular_user).count() == 0


# ---- EmailAddress CRUD ------------------------------------------------------


@pytest.mark.django_db
def test_email_address_list_filter_by_user(api_client, regular_user):
    response = api_client.get(reverse("v1:admin-email-address-list"), {"user": str(regular_user.id)})
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()
    assert {row["email"] for row in rows} == {"alice@example.com"}


@pytest.mark.django_db
def test_email_address_create_lowercases_email(api_client, regular_user):
    response = api_client.post(
        reverse("v1:admin-email-address-list"),
        data={"user": regular_user.id, "email": "Alice+Alt@Example.com", "verified": False, "primary": False},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED, response.json()
    assert EmailAddress.objects.filter(user=regular_user, email="alice+alt@example.com").exists()


@pytest.mark.django_db
def test_email_address_partial_update_toggle_verified(api_client, regular_user):
    ea = EmailAddress.objects.create(user=regular_user, email="alt@example.com", verified=False, primary=False)
    response = api_client.patch(
        reverse("v1:admin-email-address-detail", kwargs={"pk": ea.id}),
        data={"verified": True},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    ea.refresh_from_db()
    assert ea.verified is True


@pytest.mark.django_db
def test_email_address_destroy(api_client, regular_user):
    ea = EmailAddress.objects.create(user=regular_user, email="alt@example.com", verified=False, primary=False)
    response = api_client.delete(reverse("v1:admin-email-address-detail", kwargs={"pk": ea.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT
    assert not EmailAddress.objects.filter(pk=ea.id).exists()


# ---- Nested via UserExt -----------------------------------------------------


@pytest.mark.django_db
def test_user_retrieve_exposes_nested_collections(api_client, regular_user):
    response = api_client.get(reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}))
    assert response.status_code == http.HTTPStatus.OK
    body = response.json()
    assert "email_addresses" in body
    assert "social_accounts" in body
    assert {ea["email"] for ea in body["email_addresses"]} == {"alice@example.com"}
    assert {sa["uid"] for sa in body["social_accounts"]} == {"alice-google-1"}


@pytest.mark.django_db
def test_user_patch_email_addresses_add_update_remove(api_client, regular_user):
    existing_ea = EmailAddress.objects.get(user=regular_user)
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={
            "email_addresses": [
                # 기존 EA 의 verified 토글
                {"id": str(existing_ea.id), "email": existing_ea.email, "verified": False, "primary": True},
                # 새 EA 추가
                {"email": "alice+new@example.com", "verified": False, "primary": False},
            ],
        },
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    existing_ea.refresh_from_db()
    assert existing_ea.verified is False
    assert EmailAddress.objects.filter(user=regular_user, email="alice+new@example.com").exists()


@pytest.mark.django_db
def test_user_patch_email_addresses_replace_with_subset(api_client, regular_user):
    extra = EmailAddress.objects.create(user=regular_user, email="alt@example.com", verified=False, primary=False)
    primary = EmailAddress.objects.get(user=regular_user, primary=True)
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={
            "email_addresses": [
                {"id": str(primary.id), "email": primary.email, "verified": True, "primary": True},
            ],
        },
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert not EmailAddress.objects.filter(pk=extra.id).exists()
    assert EmailAddress.objects.filter(pk=primary.id).exists()


@pytest.mark.django_db
def test_user_patch_remove_social_account_with_other_remaining_preserves_emails(api_client, multi_social_user):
    keep = SocialAccount.objects.get(user=multi_social_user, provider="kakao")
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": multi_social_user.id}),
        data={"social_accounts": [{"id": str(keep.id)}]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert SocialAccount.objects.filter(user=multi_social_user).count() == 1
    assert EmailAddress.objects.filter(user=multi_social_user).count() == 1


@pytest.mark.django_db
def test_user_patch_remove_last_social_account_cascades_to_emails(api_client, regular_user):
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={"social_accounts": []},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert SocialAccount.objects.filter(user=regular_user).count() == 0
    assert EmailAddress.objects.filter(user=regular_user).count() == 0


@pytest.mark.django_db
def test_user_patch_social_accounts_with_other_users_sa_rejected(api_client, regular_user, multi_social_user):
    # 다른 user 의 SocialAccount id 를 보내면 ownership 검증으로 거부.
    other_sa = SocialAccount.objects.filter(user=multi_social_user).first()
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={"social_accounts": [{"id": other_sa.id}]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    # 거부됐으므로 양쪽 user 의 기존 데이터 유지.
    assert SocialAccount.objects.filter(user=regular_user).count() == 1
    assert EmailAddress.objects.filter(user=regular_user).count() == 1
    assert SocialAccount.objects.filter(user=multi_social_user).count() == 2


@pytest.mark.django_db
def test_user_patch_social_accounts_create_attempt_rejected(api_client, regular_user):
    # id 누락 → DRF UUIDField required 로 거부
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={"social_accounts": [{"provider": "naver", "uid": "x"}]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert SocialAccount.objects.filter(user=regular_user).count() == 1


@pytest.mark.django_db
def test_user_patch_social_accounts_ignores_readonly_field_changes(api_client, regular_user):
    sa = SocialAccount.objects.get(user=regular_user)
    original_uid = sa.uid
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={"social_accounts": [{"id": str(sa.id), "uid": "changed-uid", "extra_data": {"x": 1}}]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    sa.refresh_from_db()
    assert sa.uid == original_uid  # read_only 라 변경 무시


@pytest.mark.django_db
def test_user_patch_clear_sa_with_new_email_addresses_rejected(api_client, regular_user):
    # SA=[] cascade 가 EA 도 즉시 삭제하므로, 새 EA 입력과 같은 PATCH 로 묶이면 거부.
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={
            "social_accounts": [],
            "email_addresses": [{"email": "alice+new@example.com", "verified": False, "primary": False}],
        },
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST, response.json()
    # 거부됐으므로 기존 SA/EA 유지, 새 EA 도 생성되지 않음.
    assert SocialAccount.objects.filter(user=regular_user).count() == 1
    assert EmailAddress.objects.filter(user=regular_user).count() == 1
    assert not EmailAddress.objects.filter(email="alice+new@example.com").exists()


@pytest.mark.django_db
def test_user_patch_clear_sa_with_empty_email_addresses_allowed(api_client, regular_user):
    # 두 컬렉션 모두 빈 리스트는 "전부 정리" 의도가 명확 — 허용.
    response = api_client.patch(
        reverse("v1:admin-user-detail", kwargs={"pk": regular_user.id}),
        data={"social_accounts": [], "email_addresses": []},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert SocialAccount.objects.filter(user=regular_user).count() == 0
    assert EmailAddress.objects.filter(user=regular_user).count() == 0
