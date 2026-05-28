import logging
import traceback
from typing import Any, Literal
from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.base import Provider
from core.logger.util.django_helper import get_request_log_data
from django.conf import settings
from django.http.request import HttpRequest

# allauth.socialaccount.providers.base.AuthError 상수의 가능한 값 (UNKNOWN / CANCELLED / DENIED)
SocialAuthError = Literal["unknown", "cancelled", "denied"]

request_logger = logging.getLogger("request_logger")


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False


class SocialAccountLoggingAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest, sociallogin: SocialLogin) -> bool:
        return True

    def on_authentication_error(
        self,
        request: HttpRequest,
        provider: Provider | str,
        error: SocialAuthError | None = None,
        exception: Exception | None = None,
        extra_context: dict | None = None,
    ) -> None:
        # headless RedirectToProviderView 는 form 검증 실패 시 provider 를 Provider 인스턴스가 아닌 raw string id 로 넘김.
        if isinstance(provider, str):
            provider_data = {"id": provider, "name": None, "slug": None}
        else:
            provider_data = {"id": provider.id, "name": provider.name, "slug": provider.get_slug()}

        request_logger.info(
            msg="allauth_authentication_error",
            extra={
                "data": {
                    "request": get_request_log_data(request),
                    "provider": provider_data,
                    "error": error,
                    "exception": "".join(traceback.format_exception(exception)),
                    "extra_context_keys": extra_context.keys() if extra_context else None,
                },
            },
        )


def _to_origin(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    if not parsed.netloc:
        return None
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def _allowed_frontend_origins() -> tuple[str, ...]:
    return tuple(o for url in settings.FRONTEND_DOMAIN.main if (o := _to_origin(url)))


class PyConKRHeadlessAdapter(DefaultHeadlessAdapter):
    def get_frontend_url(self, urlname: str, **kwargs: Any) -> str | None:
        if urlname != "socialaccount_login_error":
            return super().get_frontend_url(urlname, **kwargs)

        allowed = _allowed_frontend_origins()
        origin: str | None = None
        for header in ("HTTP_X_FRONTEND_DOMAIN", "HTTP_ORIGIN", "HTTP_REFERER"):
            if (candidate := _to_origin(self.request.META.get(header))) and candidate in allowed:
                origin = candidate
                break

        if not origin:
            origin = next(iter(allowed), "")
        return f"{origin}/account/sign-in" if origin else None
