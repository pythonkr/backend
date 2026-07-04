from __future__ import annotations

from core.middleware.response_exception import ResponseException
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

HEADLESS_PROVIDER_REDIRECT_URL = reverse_lazy("headless:browser:socialaccount:redirect_to_provider")
PROVIDERS = [
    {"id": "google", "name_ko": "Google", "name_en": "Google"},
    {"id": "naver", "name_ko": "네이버", "name_en": "Naver"},
    {"id": "kakao", "name_ko": "카카오", "name_en": "Kakao"},
]
User = get_user_model()


def check_login(request: HttpRequest) -> None:
    if not request.user.is_authenticated:
        login_url = f"{reverse('account-login')}?{urlencode({'next': request.get_full_path()})}"
        raise ResponseException(redirect(login_url))


def redirect_if_authenticated(request: HttpRequest, target: str) -> None:
    if request.user.is_authenticated:
        raise ResponseException(redirect(target))


def login_target(request: HttpRequest) -> str:
    if (n := request.GET.get("next")) and url_has_allowed_host_and_scheme(n, allowed_hosts=None):
        return n
    return reverse("account-home")
