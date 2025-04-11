import http.client
import logging
import typing

from constance import config
from core.logger.util.django_helper import (
    get_aws_request_id_from_request,
    get_request_log_data,
    get_response_log_data,
)
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.deprecation import MiddlewareMixin

cloudwatch_logger = logging.getLogger("cloudwatch_logger")
slack_logger = logging.getLogger("slack_logger")


# From django-stubs
class _GetResponseCallable(typing.Protocol):
    def __call__(self, request: HttpRequest, /) -> HttpResponseBase: ...


class LoggerExtraDataType(typing.TypedDict):
    request: dict[str, typing.Any]
    response: dict[str, typing.Any]
    tag: typing.NotRequired[str]


class LoggerExtraSessionType(typing.TypedDict):
    before: dict[str, typing.Any]
    after: dict[str, typing.Any]


class LoggerExtraType(typing.TypedDict):
    aws_request_id: str
    data: LoggerExtraDataType
    session: typing.NotRequired[LoggerExtraSessionType]


class RequestResponseLogger(MiddlewareMixin):
    sync_capable = True
    async_capable = False
    get_response: _GetResponseCallable

    def __init__(self, get_response: _GetResponseCallable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        before_session_data = dict(request.session.items()) if config.DEBUG_COLLECT_SESSION_DATA else {}
        response = self.get_response(request)
        after_session_data = dict(request.session.items()) if config.DEBUG_COLLECT_SESSION_DATA else {}

        logger_extra = LoggerExtraType(
            aws_request_id=get_aws_request_id_from_request(request),
            data=LoggerExtraDataType(request=get_request_log_data(request), response=get_response_log_data(response)),
        )
        if config.DEBUG_COLLECT_SESSION_DATA:
            logger_extra["session"] = {"before": before_session_data, "after": after_session_data}

        cloudwatch_logger.info(msg="log_request", extra=logger_extra)

        if (tag := request.META.get("bad_response_slack_logger_tag")) and not (200 <= response.status_code <= 299):
            status_info = f"{response.status_code} {http.client.responses[response.status_code]}"
            msg = f"Bad Response: [{request.method}] '{request.get_full_path()}' <{status_info}>"
            logger_extra["data"]["tag"] = tag
            slack_logger.warning(msg=msg, extra=logger_extra)

        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        slack_logger.exception(
            msg="요청 처리 중 예외가 발생했습니다.",
            exc_info=(type(exception), exception, exception.__traceback__),
            extra={
                "aws_request_id": get_aws_request_id_from_request(request),
                "data": {"request": get_request_log_data(request)},
            },
        )
