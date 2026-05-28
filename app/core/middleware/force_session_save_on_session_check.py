from core.middleware.type import GetResponseCallable
from django.conf import settings
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.deprecation import MiddlewareMixin

_TARGET_PATHS = frozenset({"/authn/social/browser/v1/auth/session", "/authn/social/app/v1/auth/session"})


class ForceSessionSaveOnSessionCheckMiddleware(MiddlewareMixin):
    sync_capable = True
    async_capable = False
    get_response: GetResponseCallable

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if request.path not in _TARGET_PATHS:
            return response

        if not (session := getattr(request, "session", None)):
            return response

        if not session.session_key:
            if not settings.DEBUG:
                return response
            session["__pyconkr_bootstrap__"] = True

        session.modified = True
        return response
