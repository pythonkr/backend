from __future__ import annotations

from http import HTTPStatus

from core.const.account import MERGE_MESSAGES, MERGE_SOURCE_SESSION_KEY
from core.middleware.response_exception import ResponseException
from core.templatetags.i18n_extras import is_english
from django.db.transaction import atomic
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from user.account_views.utils import HEADLESS_PROVIDER_REDIRECT_URL, PROVIDERS, User, check_login
from user.models.merge import MergeError, UserMergeHistory


@require_GET
def merge_start(request: HttpRequest) -> HttpResponse:
    check_login(request)
    return render(
        request,
        "user/merge_start.html",
        {
            "providers": PROVIDERS,
            "redirect_url": HEADLESS_PROVIDER_REDIRECT_URL,
            "callback_url": reverse("account-merge-start"),
            "process": "connect",
            "user": request.user,
        },
    )


@require_http_methods(["GET", "POST"])
def merge_confirm(request: HttpRequest) -> HttpResponse:
    check_login(request)
    source = _merge_source(request)

    if request.method == "GET":
        return render(request, "user/merge_confirm.html", _confirm_context(source, request.user))

    try:
        with atomic():
            UserMergeHistory.assert_self_mergeable(source, request.user)
            UserMergeHistory.objects.create(source=source, target=request.user).merge()
    except MergeError as e:
        context = _confirm_context(source, request.user, error=e.localized(en=is_english()))
        return render(request, "user/merge_confirm.html", context)

    request.session.pop(MERGE_SOURCE_SESSION_KEY, None)
    return render(request, "user/merge_result.html", {"target": request.user})


def _merge_source(request: HttpRequest) -> User:
    source_id = request.session.get(MERGE_SOURCE_SESSION_KEY)
    if source_id and source_id != request.user.pk and (source := User.objects.filter(pk=source_id).first()):
        return source
    raise ResponseException(
        render(
            request,
            "user/merge_result.html",
            {"error": MERGE_MESSAGES["no_source"]["en" if is_english() else "ko"]},
            status=HTTPStatus.BAD_REQUEST,
        )
    )


def _confirm_context(source: User, target: User, *, error: str | None = None) -> dict:
    if error is None:
        try:
            UserMergeHistory.assert_self_mergeable(source, target)
        except MergeError as e:
            error = e.localized(en=is_english())
    return {"source": source, "target": target, "error": error}
