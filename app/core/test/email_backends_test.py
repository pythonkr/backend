import base64
from datetime import UTC, datetime, timedelta
from smtplib import SMTPAuthenticationError
from unittest.mock import MagicMock, patch

import pytest
from core.email_backends import (
    _ACCESS_TOKEN_TTL_BUFFER,
    GmailOAuth2Backend,
    _access_token_cache,
)
from external_api.google_oauth2.models import GoogleOAuth2
from user.models import UserExt


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


@pytest.fixture
def google_oauth_record(system_user):
    return GoogleOAuth2.objects.create(  # nosec: B106
        refresh_token="rt-test",
        created_by=system_user,
        updated_by=system_user,
    )


@pytest.fixture(autouse=True)
def clear_access_token_cache():
    _access_token_cache.clear()
    yield
    _access_token_cache.clear()


@pytest.fixture
def mock_token_endpoint():
    """Google OAuth2 token endpoint를 mock — 기본 응답: tok-1, expires_in=3600."""
    with patch("core.email_backends.httpx_post") as mock:
        response = MagicMock()
        response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        response.raise_for_status.return_value = response
        mock.return_value = response
        yield mock


@pytest.fixture
def backend():
    return GmailOAuth2Backend()


@pytest.mark.django_db
class TestAccessTokenCaching:
    def test_first_access_fetches_from_google(self, backend, google_oauth_record, mock_token_endpoint):
        token = backend._access_token
        assert token == "tok-1"  # nosec: B105
        assert mock_token_endpoint.call_count == 1

    def test_subsequent_access_uses_cache(self, backend, google_oauth_record, mock_token_endpoint):
        backend._access_token  # warm cache
        backend._access_token
        backend._access_token
        # 한 번만 호출되어야 함
        assert mock_token_endpoint.call_count == 1

    def test_expired_token_triggers_refresh(self, backend, google_oauth_record, mock_token_endpoint):
        # 이미 만료된 캐시 entry 시뮬레이션
        _access_token_cache[google_oauth_record.refresh_token] = (
            "stale",
            datetime.now(UTC) - timedelta(seconds=10),
        )
        mock_token_endpoint.return_value.json.return_value = {"access_token": "tok-fresh", "expires_in": 3600}

        token = backend._access_token

        assert token == "tok-fresh"  # nosec: B105
        assert mock_token_endpoint.call_count == 1

    def test_token_cached_with_ttl_minus_buffer(self, backend, google_oauth_record, mock_token_endpoint):
        before = datetime.now(UTC)
        backend._access_token
        after = datetime.now(UTC)

        _, expires_at = _access_token_cache[google_oauth_record.refresh_token]
        # expires_at은 (now + 1h - 60s) 범위 안에 있어야 함
        assert before + timedelta(hours=1) - _ACCESS_TOKEN_TTL_BUFFER <= expires_at
        assert expires_at <= after + timedelta(hours=1) - _ACCESS_TOKEN_TTL_BUFFER

    def test_default_ttl_when_expires_in_missing(self, backend, google_oauth_record, mock_token_endpoint):
        # expires_in이 응답에 없으면 기본 1시간 사용
        mock_token_endpoint.return_value.json.return_value = {"access_token": "tok-x"}
        backend._access_token

        _, expires_at = _access_token_cache[google_oauth_record.refresh_token]
        approx = datetime.now(UTC) + timedelta(hours=1) - _ACCESS_TOKEN_TTL_BUFFER
        assert abs((expires_at - approx).total_seconds()) < 5

    def test_no_oauth_record_raises(self, backend):
        with pytest.raises(RuntimeError, match="No GoogleOAuth2 refresh token configured"):
            backend._access_token

    def test_uses_latest_active_record(self, system_user, backend, mock_token_endpoint):
        rt_old = "rt-old"  # nosec: B105
        rt_new = "rt-new"  # nosec: B105
        GoogleOAuth2.objects.create(refresh_token=rt_old, created_by=system_user, updated_by=system_user)
        GoogleOAuth2.objects.create(refresh_token=rt_new, created_by=system_user, updated_by=system_user)

        backend._access_token

        called_with = mock_token_endpoint.call_args.kwargs["data"]
        assert called_with["refresh_token"] == rt_new


@pytest.mark.django_db
class TestAuthenticateXOAuth2:
    def test_sasl_payload_format(self, backend, google_oauth_record, mock_token_endpoint):
        backend.username = "user@example.com"
        backend.connection = MagicMock()
        backend.connection.docmd.return_value = (235, b"OK")

        backend._authenticate_xoauth2()

        cmd, payload = backend.connection.docmd.call_args.args
        assert cmd == "AUTH"
        assert payload.startswith("XOAUTH2 ")
        len_prefix = len("XOAUTH2 ")
        decoded = base64.b64decode(payload[len_prefix:]).decode()
        assert decoded == "user=user@example.com\x01auth=Bearer tok-1\x01\x01"

    def test_non_235_response_raises_authentication_error(self, backend, google_oauth_record, mock_token_endpoint):
        backend.username = "user@example.com"
        backend.connection = MagicMock()
        backend.connection.docmd.return_value = (535, b"Auth failed")

        with pytest.raises(SMTPAuthenticationError):
            backend._authenticate_xoauth2()

    def test_missing_username_raises(self, backend):
        backend.username = ""
        with pytest.raises(SMTPAuthenticationError, match="EMAIL_HOST_USER"):
            backend._authenticate_xoauth2()
