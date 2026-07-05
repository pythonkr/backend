import pytest
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from core.authn.allauth_adapter import SocialAccountLoggingAdapter
from core.const.account import MERGE_SOURCE_SESSION_KEY
from django.urls import reverse
from shop.order.models import Order
from user.account_views.utils import HEADLESS_PROVIDER_REDIRECT_URL
from user.models import UserExt
from user.models.merge import UserMergeHistory


@pytest.fixture
def source_user(db) -> UserExt:
    return UserExt.objects.create_user(username="source", email="source@example.com")


@pytest.fixture
def target_user(db) -> UserExt:
    return UserExt.objects.create_user(username="target", email="target@example.com")


def _stash_source(client, source):
    session = client.session
    session[MERGE_SOURCE_SESSION_KEY] = source.pk
    session.save()


# ---- MergeConfirmView ---------------------------------------------------------


def test_confirm_get_shows_both_accounts(client, source_user, target_user):
    client.force_login(target_user)
    _stash_source(client, source_user)

    response = client.get(reverse("account-merge-confirm"))

    assert response.status_code == 200
    assert b"source@example.com" in response.content
    assert b"target@example.com" in response.content


def test_confirm_post_executes_merge(client, source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")
    client.force_login(target_user)
    _stash_source(client, source_user)

    response = client.post(reverse("account-merge-confirm"))

    assert response.status_code == 200
    order.refresh_from_db()
    source_user.refresh_from_db()
    assert order.user_id == target_user.id
    assert source_user.is_active is False
    assert source_user.merged_to_id == target_user.id
    assert MERGE_SOURCE_SESSION_KEY not in client.session


def test_confirm_post_sets_self_merge(client, source_user, target_user):
    client.force_login(target_user)
    _stash_source(client, source_user)

    client.post(reverse("account-merge-confirm"))

    history = UserMergeHistory.objects.get(source=source_user, target=target_user)
    assert history.created_by_id == target_user.id
    assert history.is_self_merge is True


def test_confirm_blocks_when_source_has_unverified_email(client, source_user, target_user):
    EmailAddress.objects.create(user=source_user, email="extra@example.com", verified=False)
    client.force_login(target_user)
    _stash_source(client, source_user)

    response = client.post(reverse("account-merge-confirm"))

    source_user.refresh_from_db()
    assert source_user.is_active is True  # 병합 안 됨
    assert b"\xec\x9d\xb8\xec\xa6\x9d" in response.content  # "인증" 안내 노출


def test_confirm_no_source_in_session_returns_400(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-merge-confirm"))

    assert response.status_code == 400


def test_confirm_requires_authentication(client, source_user):
    _stash_source(client, source_user)

    response = client.get(reverse("account-merge-confirm"))

    assert response.status_code == 302
    assert reverse("account-login") in response["Location"]


def test_start_lists_provider_forms(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-merge-start"))

    assert response.status_code == 200
    assert HEADLESS_PROVIDER_REDIRECT_URL.encode() in response.content
    assert b'name="process" value="connect"' in response.content


def test_merged_account_session_is_logged_out(client, source_user, target_user):
    UserMergeHistory.objects.create(source=source_user, target=target_user).merge()
    client.force_login(source_user)  # 병합된(dead) 계정으로 남은 세션

    response = client.get(reverse("account-home"))

    assert response.status_code == 302
    assert "merged=1" in response["Location"]
    assert "_auth_user_id" not in client.session


def test_login_shows_merged_notice(client, db):
    response = client.get(reverse("account-login") + "?merged=1")

    assert response.status_code == 200
    assert "병합".encode() in response.content


# ---- AccountLoginView ---------------------------------------------------------


def test_login_page_renders_provider_forms(client, db):
    response = client.get(reverse("account-login"))

    assert response.status_code == 200
    assert HEADLESS_PROVIDER_REDIRECT_URL.encode() in response.content
    assert b'name="process" value="login"' in response.content


def test_login_redirects_authenticated_user_to_home(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-login"))

    assert response.status_code == 302
    assert response["Location"] == reverse("account-home")


def test_home_requires_authentication(client, db):
    response = client.get(reverse("account-home"))

    assert response.status_code == 302
    assert reverse("account-login") in response["Location"]


def test_home_links_to_merge(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-home"))

    assert response.status_code == 200
    assert reverse("account-merge-start").encode() in response.content


# ---- PasswordLoginView --------------------------------------------------------


@pytest.fixture
def password_user(db) -> UserExt:
    return UserExt.objects.create_user(username="pw", email="pw@example.com", password="s3cret-pw-123")  # nosec B106


def test_password_login_page_renders_form(client, db):
    response = client.get(reverse("account-password-login"))

    assert response.status_code == 200
    assert b'name="login"' in response.content
    assert b'name="password"' in response.content


def test_login_page_links_to_password_login(client, db):
    response = client.get(reverse("account-login"))

    assert reverse("account-password-login").encode() in response.content


def test_password_login_success_authenticates_and_redirects(client, password_user):
    response = client.post(reverse("account-password-login"), {"login": "pw@example.com", "password": "s3cret-pw-123"})

    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(password_user.pk)


def test_password_login_wrong_password_shows_error(client, password_user):
    response = client.post(reverse("account-password-login"), {"login": "pw@example.com", "password": "wrong"})

    assert response.status_code == 400
    assert "_auth_user_id" not in client.session


def test_password_login_redirects_authenticated_user(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-password-login"))

    assert response.status_code == 302
    assert response["Location"] == reverse("account-home")


# ---- MergePasswordView --------------------------------------------------------


def test_merge_password_page_renders_form(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-merge-password"))

    assert response.status_code == 200
    assert b'name="login"' in response.content
    assert b'name="password"' in response.content


def test_merge_password_valid_stashes_source_and_redirects(client, target_user, password_user):
    client.force_login(target_user)

    response = client.post(
        reverse("account-merge-password"),
        {"login": "pw@example.com", "password": "s3cret-pw-123"},  # nosec B106
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("account-merge-confirm")
    assert client.session[MERGE_SOURCE_SESSION_KEY] == password_user.pk
    assert client.session.get("_auth_user_id") == str(target_user.pk)  # 세션 유저는 target 그대로(login 안 함)


def test_merge_password_wrong_password_shows_error(client, target_user, password_user):
    client.force_login(target_user)

    response = client.post(reverse("account-merge-password"), {"login": "pw@example.com", "password": "wrong"})

    assert response.status_code == 400
    assert MERGE_SOURCE_SESSION_KEY not in client.session


def test_merge_password_own_account_rejected(client, password_user):
    client.force_login(password_user)

    response = client.post(
        reverse("account-merge-password"),
        {"login": "pw@example.com", "password": "s3cret-pw-123"},  # nosec B106
    )

    assert response.status_code == 400
    assert MERGE_SOURCE_SESSION_KEY not in client.session


def test_merge_password_rejects_passwordless_source(client, target_user, source_user):
    # source_user 는 비밀번호 없음(SNS 전용) → 비번 경로로는 소스 지정 불가, SNS 재인증을 써야 함.
    client.force_login(target_user)

    response = client.post(
        reverse("account-merge-password"),
        {"login": "source@example.com", "password": "anything"},  # nosec B106
    )

    assert response.status_code == 400
    assert MERGE_SOURCE_SESSION_KEY not in client.session


def test_merge_password_requires_authentication(client, password_user):
    response = client.get(reverse("account-merge-password"))

    assert response.status_code == 302
    assert reverse("account-login") in response["Location"]


def test_start_links_to_password_merge(client, target_user):
    client.force_login(target_user)

    response = client.get(reverse("account-merge-start"))

    assert reverse("account-merge-password").encode() in response.content


# ---- 호스트 스코프 라우팅 (accounts.*) ----------------------------------------


def test_accounts_host_serves_login_at_root(client, db):
    response = client.get("/login/", HTTP_HOST="accounts.pycon.kr")

    assert response.status_code == 200
    assert HEADLESS_PROVIDER_REDIRECT_URL.encode() in response.content


def test_default_host_has_no_root_login(client, db):
    # accounts.* 가 아니면 /login/ 이 아니라 /account/login/ 이어야 한다.
    assert client.get("/login/").status_code == 404
    assert client.get(reverse("account-login")).status_code == 200


# ---- pre_social_login adapter hook -------------------------------------------


def test_pre_social_login_triggers_merge_confirm(rf, source_user, target_user):
    account = SocialAccount.objects.create(user=source_user, provider="google", uid="src-google", extra_data={})
    sociallogin = SocialLogin(user=source_user, account=account)
    sociallogin.state = {"process": "connect"}
    request = rf.get("/")
    request.user = target_user
    request.session = {}

    with pytest.raises(ImmediateHttpResponse):
        SocialAccountLoggingAdapter().pre_social_login(request, sociallogin)

    assert request.session[MERGE_SOURCE_SESSION_KEY] == source_user.pk


def test_pre_social_login_ignores_own_account(rf, source_user):
    account = SocialAccount.objects.create(user=source_user, provider="google", uid="own", extra_data={})
    sociallogin = SocialLogin(user=source_user, account=account)
    sociallogin.state = {"process": "connect"}
    request = rf.get("/")
    request.user = source_user  # 같은 계정 재연결 — 병합 아님
    request.session = {}

    SocialAccountLoggingAdapter().pre_social_login(request, sociallogin)  # no raise

    assert MERGE_SOURCE_SESSION_KEY not in request.session


def test_pre_social_login_ignores_plain_login(rf, source_user, target_user):
    account = SocialAccount.objects.create(user=source_user, provider="google", uid="src-google", extra_data={})
    sociallogin = SocialLogin(user=source_user, account=account)
    sociallogin.state = {"process": "login"}  # connect 가 아니면 무시
    request = rf.get("/")
    request.user = target_user
    request.session = {}

    SocialAccountLoggingAdapter().pre_social_login(request, sociallogin)  # no raise

    assert MERGE_SOURCE_SESSION_KEY not in request.session


# ---- 다국어 (en) --------------------------------------------------------------


def test_login_page_english_via_accept_language(client, db):
    response = client.get(reverse("account-login"), HTTP_ACCEPT_LANGUAGE="en")

    assert b"Sign in with Google" in response.content


def test_confirm_english_via_accept_language(client, source_user, target_user):
    client.force_login(target_user)
    _stash_source(client, source_user)

    response = client.get(reverse("account-merge-confirm"), HTTP_ACCEPT_LANGUAGE="en")

    assert b"Confirm account merge" in response.content
    assert b"Account to keep" in response.content


def test_confirm_english_error_message(client, source_user, target_user):
    EmailAddress.objects.create(user=source_user, email="extra@example.com", verified=False)
    client.force_login(target_user)
    _stash_source(client, source_user)

    response = client.post(reverse("account-merge-confirm"), HTTP_ACCEPT_LANGUAGE="en")

    source_user.refresh_from_db()
    assert source_user.is_active is True  # 병합 안 됨
    assert b"unverified email" in response.content  # 영어 에러 메시지
