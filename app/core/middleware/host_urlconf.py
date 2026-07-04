from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class HostUrlconfMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.rules = getattr(settings, "HOST_URLCONFS", [])

    def __call__(self, request: HttpRequest) -> HttpResponse:
        host = request.get_host().partition(":")[0]
        for pattern, urlconf in self.rules:
            if pattern.match(host):
                request.urlconf = urlconf
                break
        return self.get_response(request)
