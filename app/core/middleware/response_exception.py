from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class ResponseException(Exception):
    def __init__(self, response: HttpResponse) -> None:
        super().__init__(response)
        self.response = response


class ResponseExceptionMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        if isinstance(exception, ResponseException):
            return exception.response
        return None
