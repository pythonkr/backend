from core.middleware.type import GetResponseCallable
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

        session = getattr(request, "session", None)
        if session is None or not session.session_key:
            return response

        session.modified = True
        return response
