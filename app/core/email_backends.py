from base64 import b64encode
from datetime import UTC, datetime, timedelta
from logging import getLogger
from smtplib import SMTPAuthenticationError
from typing import cast

from core.const.google_api import GOOGLE_OAUTH2_TOKEN_URI
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from external_api.google_oauth2.models import GoogleOAuth2
from httpx import post as httpx_post

logger = getLogger(__name__)

# Google OAuth2 access token은 보통 1시간 유효. 만료 60초 전부터 만료된 것으로 간주해 재발급(clock skew + race buffer).
_ACCESS_TOKEN_DEFAULT_TTL = timedelta(hours=1)
_ACCESS_TOKEN_TTL_BUFFER = timedelta(seconds=60)
# refresh_token → (access_token, expires_at: aware UTC)
_access_token_cache: dict[str, tuple[str, datetime]] = {}


class GmailOAuth2Backend(EmailBackend):
    def open(self) -> bool:
        if self.connection:
            return False

        # 부모 EmailBackend.open()에 connect/STARTTLS/EHLO를 위임하고, 여기는 XOAUTH2만 추가. password를 비워 부모의 LOGIN 단계는 건너뛰게 함.
        saved_password = self.password
        self.password = ""  # nosec: B105 — 부모의 LOGIN 단계 건너뛰기 위해 일시적으로 비움. 실제 인증은 XOAUTH2.
        try:
            opened = super().open()
            if not opened:
                return opened
            self._authenticate_xoauth2()
            return True
        except OSError:
            if not self.fail_silently:
                raise
            return False
        finally:
            self.password = saved_password

    @property
    def _access_token(self) -> str:
        if not (
            record := cast(GoogleOAuth2 | None, GoogleOAuth2.objects.filter_active().order_by("-created_at").first())
        ):
            raise RuntimeError(
                "No GoogleOAuth2 refresh token configured. Run /v1/external-api/google-oauth2/authorize first.",
            )
        refresh_token = cast(str, record.refresh_token)

        access_token, expires_at = _access_token_cache.get(refresh_token, (None, None))
        if access_token and expires_at and expires_at > datetime.now(UTC):
            return access_token

        payload = (
            httpx_post(
                url=GOOGLE_OAUTH2_TOKEN_URI,
                data={
                    "client_id": settings.GOOGLE_CLOUD.CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLOUD.CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10.0,
            )
            .raise_for_status()
            .json()
        )

        access_token = payload["access_token"]
        expires_in = timedelta(seconds=payload.get("expires_in", _ACCESS_TOKEN_DEFAULT_TTL.total_seconds()))
        _access_token_cache[refresh_token] = (access_token, datetime.now(UTC) + expires_in - _ACCESS_TOKEN_TTL_BUFFER)

        return access_token

    def _authenticate_xoauth2(self) -> None:
        if not self.username:
            raise SMTPAuthenticationError(530, b"EMAIL_HOST_USER must be set to the Gmail address.")

        auth_payload = f"user={self.username}\x01auth=Bearer {self._access_token}\x01\x01"
        auth_payload = f"XOAUTH2 {b64encode(auth_payload.encode()).decode()}"
        code, response = self.connection.docmd("AUTH", auth_payload)
        if code != 235:
            raise SMTPAuthenticationError(code, response)
