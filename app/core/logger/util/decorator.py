import collections.abc
import logging
import typing

from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from rest_framework.request import Request

logger = logging.getLogger(__name__)
slack_logger = logging.getLogger("slack_logger")

ViewFuncType = collections.abc.Callable[[HttpRequest, typing.Any, typing.Any], HttpResponseBase]


def bad_response_slack_logger(tag: str) -> collections.abc.Callable[[ViewFuncType], ViewFuncType]:
    def wrapper(view_func: ViewFuncType) -> ViewFuncType:
        def inner_wrapper(*args: typing.Any, **kwargs: typing.Any) -> HttpResponseBase:
            try:
                request: Request | HttpRequest = args[1]
                request.META["bad_response_slack_logger_tag"] = tag
            except Exception:
                logger.warning("bad_response_slack_logger: logging disabled as args length is less than 2")
            return view_func(*args, **kwargs)

        return inner_wrapper

    return wrapper
