from __future__ import annotations

from http import HTTPStatus

from allauth.account.forms import LoginForm
from core.const.account import MERGE_MESSAGES, MERGE_SOURCE_SESSION_KEY
from core.middleware.response_exception import ResponseException
from core.templatetags.i18n_extras import is_english
from django.contrib.auth import get_user_model
from django.db.transaction import atomic
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views import View
from user.models.merge import MergeError, UserMergeHistory

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


def _login_target(request: HttpRequest) -> str:
    if (n := request.GET.get("next")) and url_has_allowed_host_and_scheme(n, allowed_hosts=None):
        return n
    return reverse("account-home")


class AccountHomeView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        check_login(request)
        return render(request, "user/account_home.html", {"user": request.user})


class AccountLoginView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        target = _login_target(request)
        redirect_if_authenticated(request, target)
        return render(
            request=request,
            template_name="user/account_login.html",
            context={
                "providers": PROVIDERS,
                "redirect_url": HEADLESS_PROVIDER_REDIRECT_URL,
                "callback_url": target,
                "process": "login",
            },
        )


class PasswordLoginView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        redirect_if_authenticated(request, _login_target(request))
        return render(request, "user/account_password_login.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        target = _login_target(request)
        redirect_if_authenticated(request, target)

        form = LoginForm(data=request.POST, request=request)
        if form.is_valid():
            return form.login(request, redirect_url=target)

        return render(
            request=request,
            template_name="user/account_password_login.html",
            context={"error": MERGE_MESSAGES["wrong_account_or_password"]["en" if is_english() else "ko"]},
            status=HTTPStatus.BAD_REQUEST,
        )


class MergeStartView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        check_login(request)
        return render(
            request=request,
            template_name="user/merge_start.html",
            context={
                "providers": PROVIDERS,
                "redirect_url": HEADLESS_PROVIDER_REDIRECT_URL,
                "callback_url": reverse("account-merge-start"),
                "process": "connect",
                "user": request.user,
            },
        )


class MergeConfirmView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        check_login(request)
        return render(
            request=request,
            template_name="user/merge_confirm.html",
            context=self._confirm_context(self._source(request), request.user),
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        check_login(request)
        source = self._source(request)

        try:
            with atomic():
                UserMergeHistory.assert_self_mergeable(source, request.user)
                UserMergeHistory.objects.create(source=source, target=request.user).merge()
        except MergeError as e:
            return render(
                request=request,
                template_name="user/merge_confirm.html",
                context=self._confirm_context(source, request.user, error=e.localized(en=is_english())),
            )

        request.session.pop(MERGE_SOURCE_SESSION_KEY, None)
        return render(request, "user/merge_result.html", {"target": request.user})

    def _source(self, request: HttpRequest) -> User:
        source_id = request.session.get(MERGE_SOURCE_SESSION_KEY)
        if source_id and source_id != request.user.pk and (source := User.objects.filter(pk=source_id).first()):
            return source
        raise ResponseException(
            render(
                request=request,
                template_name="user/merge_result.html",
                context={"error": MERGE_MESSAGES["no_source"]["en" if is_english() else "ko"]},
                status=HTTPStatus.BAD_REQUEST,
            )
        )

    def _confirm_context(self, source: User, target: User, *, error: str | None = None) -> dict:
        if error is None:
            try:
                UserMergeHistory.assert_self_mergeable(source, target)
            except MergeError as e:
                error = e.localized(en=is_english())
        return {"source": source, "target": target, "error": error}
