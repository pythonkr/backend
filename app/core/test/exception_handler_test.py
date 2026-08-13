import pytest
from core.exception_handler import (
    CHECK_VIOLATION,
    EXCLUSION_VIOLATION,
    UNIQUE_VIOLATION,
    ConflictError,
    DBConstraintExceptionHandler,
)
from django.db import IntegrityError
from model_bakery import baker
from rest_framework import exceptions
from rest_framework.status import HTTP_409_CONFLICT
from rest_framework.test import APIClient
from rest_framework.validators import UniqueValidator
from user.models import UserExt

NOT_NULL_VIOLATION = "23502"

# 어드민 Event 라우트는 basename 이 공개 Event 라우트("event")와 겹쳐 reverse 로 지목할 수 없다.
EVENT_ADMIN_LIST_URL = "/v1/admin-api/event/event/"


class _PgError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _integrity_error(sqlstate: str) -> IntegrityError:
    exc = IntegrityError("constraint violation")
    exc.__cause__ = _PgError(sqlstate)
    return exc


def _convert(exc: Exception) -> Exception:
    return DBConstraintExceptionHandler(exc, {}).convert_known_exceptions(exc)


@pytest.fixture
def api_client(db) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=UserExt.objects.create_superuser(username="admin", email="a@example.com"))
    return client


@pytest.mark.parametrize("sqlstate", [UNIQUE_VIOLATION, EXCLUSION_VIOLATION])
def test_conflicting_constraints_become_409(sqlstate):
    assert isinstance(_convert(_integrity_error(sqlstate)), ConflictError)


def test_check_violation_becomes_400():
    assert isinstance(_convert(_integrity_error(CHECK_VIOLATION)), exceptions.ValidationError)


def test_other_violations_stay_unhandled():
    # NOT NULL·FK 위반은 코드 결함이라 500 으로 노출돼야 한다.
    exc = _integrity_error(NOT_NULL_VIOLATION)

    assert _convert(exc) is exc


def test_integrity_error_without_db_cause_stays_unhandled():
    exc = IntegrityError("raised by hand")

    assert _convert(exc) is exc


@pytest.mark.django_db
def test_violation_reaching_the_db_returns_409_instead_of_500(api_client, monkeypatch):
    """검증 통과 후 INSERT 가 제약에 걸리는 경합을 재현 — 실제 psycopg 예외로 409 까지 확인한다."""
    monkeypatch.setattr(UniqueValidator, "__call__", lambda *args, **kwargs: None)
    event = baker.make("event.Event", name="파이콘 한국 2026")

    response = api_client.post(
        EVENT_ADMIN_LIST_URL,
        {"organization": str(event.organization_id), "name_ko": event.name},
        format="json",
    )

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["type"] == "client_error"
