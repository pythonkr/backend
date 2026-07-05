from __future__ import annotations

from http import HTTPStatus

from allauth.account.forms import LoginForm
from core.const.account import MERGE_MESSAGES
from core.templatetags.i18n_extras import is_english
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods
from user.account_views.utils import (
    HEADLESS_PROVIDER_REDIRECT_URL,
    PROVIDERS,
    check_login,
    login_target,
    redirect_if_authenticated,
)


@require_GET
def account_home(request: HttpRequest) -> HttpResponse:
    check_login(request)
    return render(request, "user/account_home.html", {"user": request.user})


@require_GET
def account_login(request: HttpRequest) -> HttpResponse:
    target = login_target(request)
    redirect_if_authenticated(request, target)
    code = request.session.pop("login_error", None)
    return render(
        request,
        "user/account_login.html",
        {
            "providers": PROVIDERS,
            "redirect_url": HEADLESS_PROVIDER_REDIRECT_URL,
            "callback_url": target,
            "process": "login",
            "error": MERGE_MESSAGES[code]["en" if is_english() else "ko"] if code in MERGE_MESSAGES else None,
        },
    )


@require_http_methods(["GET", "POST"])
def password_login(request: HttpRequest) -> HttpResponse:
    target = login_target(request)
    redirect_if_authenticated(request, target)

    if request.method == "GET":
        return render(request, "user/account_password_login.html")

    form = LoginForm(data=request.POST, request=request)
    if form.is_valid():
        return form.login(request, redirect_url=target)
    return render(
        request,
        "user/account_password_login.html",
        {"error": MERGE_MESSAGES["wrong_account_or_password"]["en" if is_english() else "ko"]},
        status=HTTPStatus.BAD_REQUEST,
    )
