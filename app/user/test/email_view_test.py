import http

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.urls import reverse
from user.models import UserExt


@pytest.fixture
def user(db) -> UserExt:
    u = UserExt.objects.create_user(username="u", email="u@example.com")
    EmailAddress.objects.create(user=u, email="u@example.com", verified=True, primary=True)
    return u


def _unverified(user: UserExt, email: str = "new@example.com") -> EmailAddress:
    return EmailAddress.objects.create(user=user, email=email, verified=False)


# ---- Auth -------------------------------------------------------------------


def test_manage_requires_login(client, db):
    response = client.get(reverse("account-email"))
    assert response.status_code == http.HTTPStatus.FOUND  # → login


def test_manage_lists_emails(client, user):
    client.force_login(user)
    response = client.get(reverse("account-email"))
    assert response.status_code == http.HTTPStatus.OK
    assert b"u@example.com" in response.content


# ---- Add + verify -----------------------------------------------------------


def test_add_creates_unverified_and_sends_confirmation(client, user, mailoutbox):
    client.force_login(user)
    response = client.post(reverse("account-email-add"), {"email": "new@example.com"})
    assert response.status_code == http.HTTPStatus.OK
    assert EmailAddress.objects.filter(user=user, email="new@example.com", verified=False).exists()
    assert len(mailoutbox) == 1
    assert "new@example.com" in mailoutbox[0].to
    assert "email/confirm/" in mailoutbox[0].body  # activate_url 포함


def test_add_duplicate_rejected(client, user):
    client.force_login(user)
    response = client.post(reverse("account-email-add"), {"email": "u@example.com"})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert EmailAddress.objects.filter(user=user).count() == 1


def test_confirm_verifies_email(client, user):
    email = _unverified(user)
    key = EmailConfirmationHMAC(email).key

    response = client.get(reverse("account-email-confirm", kwargs={"key": key}))
    assert response.status_code == http.HTTPStatus.OK
    email.refresh_from_db()
    assert email.verified is True


def test_confirm_invalid_key_rejected(client, db):
    response = client.get(reverse("account-email-confirm", kwargs={"key": "bogus-key"}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- Resend -----------------------------------------------------------------


def test_resend_unverified(client, user, mailoutbox):
    email = _unverified(user)
    client.force_login(user)
    response = client.post(reverse("account-email-resend"), {"email_id": email.pk})
    assert response.status_code == http.HTTPStatus.OK
    assert len(mailoutbox) == 1


def test_resend_verified_rejected(client, user, mailoutbox):
    client.force_login(user)
    primary = EmailAddress.objects.get(user=user)
    response = client.post(reverse("account-email-resend"), {"email_id": primary.pk})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert len(mailoutbox) == 0


# ---- Delete -----------------------------------------------------------------


def test_delete_email(client, user):
    email = _unverified(user)
    client.force_login(user)
    response = client.post(reverse("account-email-delete"), {"email_id": email.pk})
    assert response.status_code == http.HTTPStatus.OK
    assert not EmailAddress.objects.filter(pk=email.pk).exists()


def test_delete_last_email_rejected(client, user):
    # email-only 로그인이라 마지막 이메일 삭제는 차단(dangling 방지).
    client.force_login(user)
    only = EmailAddress.objects.get(user=user)
    response = client.post(reverse("account-email-delete"), {"email_id": only.pk})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert EmailAddress.objects.filter(pk=only.pk).exists()


def test_delete_primary_with_others_rejected(client, user):
    # 다른 이메일이 있을 때 대표 이메일 삭제는 거부(먼저 대표를 옮겨야 함).
    EmailAddress.objects.create(user=user, email="new@example.com", verified=True)
    client.force_login(user)
    primary = EmailAddress.objects.get(user=user, primary=True)
    response = client.post(reverse("account-email-delete"), {"email_id": primary.pk})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert EmailAddress.objects.filter(pk=primary.pk).exists()


# ---- Primary ----------------------------------------------------------------


def test_set_primary_verified(client, user):
    other = EmailAddress.objects.create(user=user, email="new@example.com", verified=True)
    client.force_login(user)
    response = client.post(reverse("account-email-primary"), {"email_id": other.pk})
    assert response.status_code == http.HTTPStatus.OK
    other.refresh_from_db()
    assert other.primary is True


def test_set_primary_unverified_rejected(client, user):
    other = _unverified(user)
    client.force_login(user)
    response = client.post(reverse("account-email-primary"), {"email_id": other.pk})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    other.refresh_from_db()
    assert other.primary is False


def test_action_on_other_users_email_rejected(client, user):
    other_user = UserExt.objects.create_user(username="o", email="o@example.com")
    other_email = EmailAddress.objects.create(user=other_user, email="o@example.com", verified=True)
    client.force_login(user)
    response = client.post(reverse("account-email-delete"), {"email_id": other_email.pk})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST  # request.user 로 스코프 → 못 찾음
    assert EmailAddress.objects.filter(pk=other_email.pk).exists()
