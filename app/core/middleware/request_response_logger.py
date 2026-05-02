import http.client
import logging
import typing

from core.logger.util.django_helper import get_request_log_data, get_response_log_data
from core.middleware.type import GetResponseCallable
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.deprecation import MiddlewareMixin

request_logger = logging.getLogger("request_logger")
slack_logger = logging.getLogger("slack_logger")


class LoggerExtraDataType(typing.TypedDict):
    request: dict[str, typing.Any]
    response: dict[str, typing.Any]
    tag: typing.NotRequired[str]


class LoggerExtraType(typing.TypedDict):
    data: LoggerExtraDataType


class RequestResponseLogger(MiddlewareMixin):
    sync_capable = True
    async_capable = False
    get_response: GetResponseCallable

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)

        logger_extra = LoggerExtraType(
            data=LoggerExtraDataType(request=get_request_log_data(request), response=get_response_log_data(response)),
        )

        request_logger.info(msg="log_request", extra=logger_extra)

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
                "data": {"request": get_request_log_data(request)},
            },
        )
