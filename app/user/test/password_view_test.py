import http
import re

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.models import EmailAddress
from allauth.account.utils import user_pk_to_url_str
from django.urls import reverse
from user.models import UserExt

PASSWORD = "sup3r-s3cret-pw"  # nosec B105
NEW_PASSWORD = "br4nd-new-s3cret"  # nosec B105
KEY_URL_RE = re.compile(r"/password/reset/key/([^/\"]+)/")


@pytest.fixture
def user(db) -> UserExt:
    u = UserExt.objects.create_user(username="u", email="u@example.com", password=PASSWORD)
    EmailAddress.objects.create(user=u, email="u@example.com", verified=True, primary=True)
    return u


@pytest.fixture
def social_user(db) -> UserExt:
    # 소셜 전용: 사용 가능한 비밀번호 없음.
    u = UserExt.objects.create_user(username="s", email="s@example.com")
    u.set_unusable_password()
    u.save()
    EmailAddress.objects.create(user=u, email="s@example.com", verified=True, primary=True)
    return u


def _make_key(u: UserExt) -> str:
    return f"{user_pk_to_url_str(u)}-{default_token_generator.make_token(u)}"


def _reset_url(u: UserExt) -> str:
    return reverse("account-password-reset-from-key", kwargs={"key": _make_key(u)})


# ---- Change (logged-in, has password) ---------------------------------------


def test_change_requires_login(client, db):
    response = client.get(reverse("account-password-change"))
    assert response.status_code == http.HTTPStatus.FOUND  # → login


def test_change_get_shows_current_password_field(client, user):
    client.force_login(user)
    response = client.get(reverse("account-password-change"))
    assert response.status_code == http.HTTPStatus.OK
    assert b"oldpassword" in response.content


def test_change_success_keeps_session(client, user):
    client.force_login(user)
    response = client.post(
        reverse("account-password-change"),
        {"oldpassword": PASSWORD, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
    )
    assert response.status_code == http.HTTPStatus.OK
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    # 세션 유지 → 이어지는 인증 페이지 접근 가능.
    assert client.get(reverse("account-home")).status_code == http.HTTPStatus.OK


def test_change_wrong_old_password_rejected(client, user):
    client.force_login(user)
    response = client.post(
        reverse("account-password-change"),
        {"oldpassword": "wrong-password", "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_change_mismatch_rejected(client, user):
    client.force_login(user)
    response = client.post(
        reverse("account-password-change"),
        {"oldpassword": PASSWORD, "password1": NEW_PASSWORD, "password2": "different-one"},
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


# ---- Set (logged-in, social-only, no password) ------------------------------


def test_set_get_hides_current_password_field(client, social_user):
    client.force_login(social_user)
    response = client.get(reverse("account-password-change"))
    assert response.status_code == http.HTTPStatus.OK
    assert b"oldpassword" not in response.content


def test_set_password_for_social_user(client, social_user):
    client.force_login(social_user)
    response = client.post(
        reverse("account-password-change"),
        {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
    )
    assert response.status_code == http.HTTPStatus.OK
    social_user.refresh_from_db()
    assert social_user.has_usable_password()
    assert social_user.check_password(NEW_PASSWORD)


# ---- Reset request ----------------------------------------------------------


def test_reset_get_renders_form(client, db):
    response = client.get(reverse("account-password-reset"))
    assert response.status_code == http.HTTPStatus.OK
    assert b'name="email"' in response.content


def test_reset_sends_email_with_key_link(client, user, mailoutbox):
    response = client.post(reverse("account-password-reset"), {"email": "u@example.com"})
    assert response.status_code == http.HTTPStatus.OK
    assert len(mailoutbox) == 1
    assert "u@example.com" in mailoutbox[0].to
    assert KEY_URL_RE.search(mailoutbox[0].body)


def test_reset_unknown_email_no_leak(client, db, mailoutbox):
    # enumeration 방지: 미가입 이메일도 동일한 성공 화면, 메일은 발송하지 않음.
    response = client.post(reverse("account-password-reset"), {"email": "nobody@example.com"})
    assert response.status_code == http.HTTPStatus.OK
    assert len(mailoutbox) == 0


def test_reset_invalid_email_format_rejected(client, db):
    response = client.post(reverse("account-password-reset"), {"email": "not-an-email"})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- Reset from key ---------------------------------------------------------


def test_reset_key_get_valid_shows_form(client, user):
    response = client.get(_reset_url(user))
    assert response.status_code == http.HTTPStatus.OK
    assert b'name="password1"' in response.content


def test_reset_key_get_invalid_rejected(client, db):
    response = client.get(reverse("account-password-reset-from-key", kwargs={"key": "bogus-key-value"}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


def test_reset_key_success(client, user):
    response = client.post(_reset_url(user), {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert response.status_code == http.HTTPStatus.OK
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert not user.check_password(PASSWORD)


def test_reset_key_mismatch_rejected(client, user):
    response = client.post(_reset_url(user), {"password1": NEW_PASSWORD, "password2": "different-one"})
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_reset_key_is_single_use(client, user):
    url = _reset_url(user)
    assert client.post(url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}).status_code == http.HTTPStatus.OK
    # 비밀번호가 바뀌면 토큰이 무효화되어 같은 링크 재사용 불가.
    assert client.get(url).status_code == http.HTTPStatus.BAD_REQUEST


def test_reset_end_to_end_via_email(client, user, mailoutbox):
    # 요청 → 메일의 실제 링크로 재설정 → 새 비밀번호로 로그인.
    client.post(reverse("account-password-reset"), {"email": "u@example.com"})
    key = KEY_URL_RE.search(mailoutbox[0].body).group(1)
    url = reverse("account-password-reset-from-key", kwargs={"key": key})

    response = client.post(url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert response.status_code == http.HTTPStatus.OK
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
