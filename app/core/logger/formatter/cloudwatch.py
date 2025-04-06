import logging
import traceback
import types
import typing

from core.logger.util.django_helper import default_json_dumps

ExcInfoType: typing.TypeAlias = tuple[type[BaseException] | None, BaseException | None, types.TracebackType | None]

DEFAULT_CLOUDWATCH_LOG_FORMAT = "[%(levelname)s]\t%(asctime)s.%(msecs)dZ\t%(levelno)s\t%(message)s\n"
DEFAULT_CLOUDWATCH_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class CloudWatchJsonFormatter(logging.Formatter):
    """
    CloudWatchJsonFormatter formats log records as JSON strings.
    example:
    >> logger.info("This is a log message", extra={"data": {"key": "value"}})
    {
        "level_name": "INFO",
        "time": "2021-08-31T16:00:00.123456Z",
        "aws_request_id": "00000000-0000-0000-0000-000000000000",
        "message": "This is a log message",
        "module": "module_name",
        "func_name": "function_name",
        "extra_data": {"key": "value"},
        "exc_info": {
            "type": "Exception",
            "message": "Exception message",
            "traceback_msg": "Traceback(most recent call last)..."
        }
    }
    """

    def __init__(
        self,
        fmt: str = DEFAULT_CLOUDWATCH_LOG_FORMAT,
        datefmt: str = DEFAULT_CLOUDWATCH_DATE_FORMAT,
        style: typing.Literal["%", "{", "$"] = "%",
        validate: bool = True,
        *,
        defaults: typing.Any | None = None,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate, defaults=defaults)

    def formatException(self, exc_info: ExcInfoType) -> dict:  # type: ignore[override]
        exc_type, exc_value, _ = exc_info
        return {
            "type": exc_type.__name__,
            "message": str(exc_value),
            "traceback_msg": "\n".join(traceback.format_exception(exc_value)),
        }

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)  # type: ignore[assignment]

        return default_json_dumps(
            {
                "level_name": record.levelname,
                "time": "%(asctime)s.%(msecs)dZ" % dict(asctime=record.asctime, msecs=record.msecs),
                "aws_request_id": getattr(record, "aws_request_id", "00000000-0000-0000-0000-000000000000"),
                "message": record.message,
                "module": record.module,
                "func_name": record.funcName,
                "extra_data": record.__dict__.get("data", {}),
                "exc_info": record.exc_text,
            },
        )
