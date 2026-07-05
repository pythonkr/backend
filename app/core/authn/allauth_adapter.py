import logging
import traceback
from typing import Any, Literal
from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.base import Provider
from allauth.socialaccount.providers.base.constants import AuthProcess
from core.const.account import MERGE_SOURCE_SESSION_KEY
from core.logger.util.django_helper import get_request_log_data
from django.conf import settings
from django.http.request import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse

# allauth.socialaccount.providers.base.AuthError 상수의 가능한 값 (UNKNOWN / CANCELLED / DENIED)
SocialAuthError = Literal["unknown", "cancelled", "denied"]

request_logger = logging.getLogger("request_logger")


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False

    def get_email_confirmation_url(self, request: HttpRequest, emailconfirmation: Any) -> str:
        return request.build_absolute_uri(reverse("account-email-confirm", kwargs={"key": emailconfirmation.key}))

    def get_reset_password_from_key_url(self, key: str) -> str:
        return self.request.build_absolute_uri(reverse("account-password-reset-from-key", kwargs={"key": key}))


class SocialAccountLoggingAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest, sociallogin: SocialLogin) -> bool:
        return True

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        # 로그인 상태에서 계정 병합으로 다른 기존 계정의 소셜 로그인을 인증 시 병합 확인 페이지로.
        if (
            sociallogin.state.get("process") == AuthProcess.CONNECT
            and request.user.is_authenticated
            and sociallogin.is_existing
            and sociallogin.user.pk != request.user.pk
        ):
            request.session[MERGE_SOURCE_SESSION_KEY] = sociallogin.user.pk
            raise ImmediateHttpResponse(redirect(reverse("account-merge-confirm")))

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

        if getattr(self.request, "urlconf", None) == "core.account_urls":
            self.request.session["login_error"] = "social_login_failed"
            return reverse("account-login", urlconf=self.request.urlconf)

        allowed = _allowed_frontend_origins()
        origin: str | None = None
        for header in ("HTTP_X_FRONTEND_DOMAIN", "HTTP_ORIGIN", "HTTP_REFERER"):
            if (candidate := _to_origin(self.request.META.get(header))) and candidate in allowed:
                origin = candidate
                break

        if not origin:
            origin = next(iter(allowed), "")
        return f"{origin}/account/sign-in" if origin else None
