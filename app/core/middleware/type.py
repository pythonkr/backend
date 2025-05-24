import typing

from django.http.request import HttpRequest
from django.http.response import HttpResponseBase


# From django-stubs
class GetResponseCallable(typing.Protocol):
    def __call__(self, request: HttpRequest, /) -> HttpResponseBase: ...
