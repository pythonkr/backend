from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from core.middleware.type import GetResponseCallable
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase, HttpResponseRedirectBase
from django.utils.deprecation import MiddlewareMixin

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class AppendSessionTokenForLocalCallbackMiddleware(MiddlewareMixin):
    """OAuth 콜백 응답이 localhost로 redirect되는 경우에 한해, redirect URL의 fragment에 #session_token=<django session key>를 덧붙임"""

    sync_capable = True
    async_capable = False
    get_response: GetResponseCallable

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if not isinstance(response, HttpResponseRedirectBase):
            return response

        if not (session_key := getattr(getattr(request, "session", None), "session_key", None)):
            return response

        if not (location := response.headers.get("Location")):
            return response

        parsed = urlparse(location)
        if (parsed.hostname or "").lower() not in LOCAL_HOSTS:
            return response

        fragment_params = dict(parse_qsl(parsed.fragment, keep_blank_values=True))
        if fragment_params.get("session_token") == session_key:
            return response
        fragment_params["session_token"] = session_key
        response["Location"] = urlunparse(parsed._replace(fragment=urlencode(fragment_params)))
        return response
