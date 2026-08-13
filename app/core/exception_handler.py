from logging import getLogger

from django.db import IntegrityError
from drf_standardized_errors.handler import ExceptionHandler
from rest_framework import exceptions, status

logger = getLogger(__name__)

UNIQUE_VIOLATION = "23505"
EXCLUSION_VIOLATION = "23P01"
CHECK_VIOLATION = "23514"

CHECK_VIOLATION_MESSAGE = "입력값이 데이터 제약 조건을 위반했습니다."


class ConflictError(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "이미 있는 데이터와 충돌합니다."
    default_code = "conflict"


class DBConstraintExceptionHandler(ExceptionHandler):
    def convert_known_exceptions(self, exc: Exception) -> Exception:
        if isinstance(exc, IntegrityError) and (converted := self._convert_integrity_error(exc)) is not None:
            logger.warning("DB constraint violation: %s", exc)
            return converted
        return super().convert_known_exceptions(exc)

    @staticmethod
    def _convert_integrity_error(exc: IntegrityError) -> exceptions.APIException | None:
        sqlstate = getattr(exc.__cause__, "sqlstate", None)
        if sqlstate in (UNIQUE_VIOLATION, EXCLUSION_VIOLATION):
            return ConflictError()
        if sqlstate == CHECK_VIOLATION:
            return exceptions.ValidationError(CHECK_VIOLATION_MESSAGE)
        return None
