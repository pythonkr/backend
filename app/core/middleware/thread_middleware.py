from core.middleware.type import GetResponseCallable
from core.util.thread_local import thread_local
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.deprecation import MiddlewareMixin


class ThreadLocalMiddleware(MiddlewareMixin):
    sync_capable = True
    async_capable = False
    get_response: GetResponseCallable

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        thread_local.current_request = request
        return self.get_response(request)
