from __future__ import annotations

from http import HTTPStatus

from allauth.account.forms import AddEmailForm
from allauth.account.internal.flows.manage_email import can_delete_email, can_mark_as_primary
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from core.const.account import EMAIL_MESSAGES
from core.middleware.response_exception import ResponseException
from core.templatetags.i18n_extras import is_english
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from user.account_views.utils import check_login


def _email_msg(code: str) -> str:
    return EMAIL_MESSAGES[code]["en" if is_english() else "ko"]


def _render_emails(
    request: HttpRequest, *, error: str | None = None, notice: str | None = None, status: HTTPStatus = HTTPStatus.OK
) -> HttpResponse:
    return render(
        request,
        "user/email_manage.html",
        {
            "user": request.user,
            "emails": EmailAddress.objects.filter(user=request.user).order_by("-primary", "-verified", "email"),
            "error": error,
            "notice": notice,
        },
        status=status,
    )


def _target_email(request: HttpRequest) -> EmailAddress:
    if email := EmailAddress.objects.filter(user=request.user, pk=request.POST.get("email_id")).first():
        return email
    raise ResponseException(_render_emails(request, error=_email_msg("not_found"), status=HTTPStatus.BAD_REQUEST))


@require_GET
def manage_emails(request: HttpRequest) -> HttpResponse:
    check_login(request)
    return _render_emails(request)


@require_POST
def add_email(request: HttpRequest) -> HttpResponse:
    check_login(request)
    form = AddEmailForm(user=request.user, data=request.POST)
    if not form.is_valid():
        return _render_emails(request, error=_email_msg("add_failed"), status=HTTPStatus.BAD_REQUEST)
    form.save(request)
    return _render_emails(request, notice=_email_msg("verification_sent"))


@require_POST
def delete_email(request: HttpRequest) -> HttpResponse:
    check_login(request)
    email = _target_email(request)
    if not can_delete_email(email):
        return _render_emails(request, error=_email_msg("cannot_delete"), status=HTTPStatus.BAD_REQUEST)
    email.remove()
    return _render_emails(request, notice=_email_msg("deleted"))


@require_POST
def resend_email(request: HttpRequest) -> HttpResponse:
    check_login(request)
    email = _target_email(request)
    if email.verified:
        return _render_emails(request, error=_email_msg("already_verified"), status=HTTPStatus.BAD_REQUEST)
    email.send_confirmation(request)
    return _render_emails(request, notice=_email_msg("resent"))


@require_POST
def set_primary_email(request: HttpRequest) -> HttpResponse:
    check_login(request)
    email = _target_email(request)
    if not can_mark_as_primary(email):
        return _render_emails(request, error=_email_msg("cannot_set_primary"), status=HTTPStatus.BAD_REQUEST)
    email.set_as_primary()
    return _render_emails(request, notice=_email_msg("primary_set"))


@require_GET
def confirm_email(request: HttpRequest, key: str) -> HttpResponse:
    confirmation = EmailConfirmationHMAC.from_key(key)
    if confirmation is None:
        context = {"error": _email_msg("invalid_link")}
        return render(request, "user/email_confirm_result.html", context, status=HTTPStatus.BAD_REQUEST)
    confirmation.confirm(request)
    return render(request, "user/email_confirm_result.html", {"email": confirmation.email_address.email})
