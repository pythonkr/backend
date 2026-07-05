from __future__ import annotations

from http import HTTPStatus

from allauth.account.forms import (
    ChangePasswordForm,
    ResetPasswordForm,
    ResetPasswordKeyForm,
    SetPasswordForm,
    UserTokenForm,
)
from core.const.account import PASSWORD_MESSAGES
from core.templatetags.i18n_extras import is_english
from django.contrib.auth import update_session_auth_hash
from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from user.account_views.utils import check_login

PASSWORD_FORM_TEMPLATE = "user/account_password_form.html"  # nosec B105 (템플릿 경로, 비밀번호 아님)


def _form_errors(form: Form) -> list[str]:
    return [str(error) for errors in form.errors.values() for error in errors]


@require_http_methods(["GET", "POST"])
def password_change(request: HttpRequest) -> HttpResponse:
    check_login(request)
    has_password = request.user.has_usable_password()
    context = {"show_current": has_password, "back_home": True}

    if request.method == "GET":
        return render(
            request=request,
            template_name=PASSWORD_FORM_TEMPLATE,
            context=context,
        )

    form = (ChangePasswordForm if has_password else SetPasswordForm)(user=request.user, data=request.POST)
    if not form.is_valid():
        context["errors"] = _form_errors(form)
        return render(
            request=request,
            template_name=PASSWORD_FORM_TEMPLATE,
            context=context,
            status=HTTPStatus.BAD_REQUEST,
        )
    form.save()
    update_session_auth_hash(request, request.user)

    return render(
        request=request,
        template_name=PASSWORD_FORM_TEMPLATE,
        context={
            "show_current": True,
            "back_home": True,
            "notice": PASSWORD_MESSAGES["changed"]["en" if is_english() else "ko"],
        },
    )


@require_http_methods(["GET", "POST"])
def password_reset(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "user/account_password_reset.html")

    form = ResetPasswordForm(data=request.POST)
    if not form.is_valid():
        return render(
            request=request,
            template_name="user/account_password_reset.html",
            context={"errors": _form_errors(form)},
            status=HTTPStatus.BAD_REQUEST,
        )
    form.save(request)

    return render(
        request=request,
        template_name="user/account_password_reset.html",
        context={"sent": True},
    )


@require_http_methods(["GET", "POST"])
def password_reset_from_key(request: HttpRequest, key: str) -> HttpResponse:
    uidb36, _, temp_key = key.partition("-")
    token_form = UserTokenForm(data={"uidb36": uidb36, "key": temp_key})
    if not token_form.is_valid():
        return render(
            request=request,
            template_name=PASSWORD_FORM_TEMPLATE,
            context={"invalid": True},
            status=HTTPStatus.BAD_REQUEST,
        )

    if request.method == "GET":
        return render(
            request=request,
            template_name=PASSWORD_FORM_TEMPLATE,
            context={"autofocus_new": True},
        )

    form = ResetPasswordKeyForm(user=token_form.reset_user, temp_key=temp_key, data=request.POST)
    if not form.is_valid():
        return render(
            request=request,
            template_name=PASSWORD_FORM_TEMPLATE,
            context={"autofocus_new": True, "errors": _form_errors(form)},
            status=HTTPStatus.BAD_REQUEST,
        )
    form.save()

    return render(
        request=request,
        template_name=PASSWORD_FORM_TEMPLATE,
        context={
            "done": True,
            "notice": PASSWORD_MESSAGES["reset_done"]["en" if is_english() else "ko"],
        },
    )
