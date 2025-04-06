import collections
import os
import http
import typing

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _check_databases() -> tuple[bool, dict[str, typing.Any]]:
    results: dict[str, dict[str, typing.Any]] = {}
    for alias in settings.DATABASES:
        results[alias] = {"success": True, "error": None}
        try:
            with connections[alias].cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError as e:
            results[alias].update({"success": False, "error": str(e)})
    return all(results[key]["success"] for key in results), results


def _check_django_migrations() -> tuple[bool, collections.defaultdict[str, list[str]]]:
    result: collections.defaultdict[str, list[str]] = collections.defaultdict(list)

    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    migration_plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    for migration_info, _ in migration_plan:
        result[migration_info.app_label].append(migration_info.name)

    return bool(migration_plan), result


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def readyz(request: HttpRequest) -> Response:
    is_dbs_ok, db_status = _check_databases()
    requires_migrations, migration_status = _check_django_migrations()
    response_data = (
        {
            "database": db_status,
            "migrations": migration_status,
            "version": settings.DEPLOYMENT_RELEASE_VERSION,
            "git_sha": os.getenv("DEPLOYMENT_GIT_HASH", ""),
        }
        if settings.DEBUG
        else {}
    )
    return Response(
        data=response_data,
        status=http.HTTPStatus.OK if is_dbs_ok and requires_migrations else http.HTTPStatus.SERVICE_UNAVAILABLE,
    )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def livez(request: HttpRequest) -> Response:
    return Response({}, status=http.HTTPStatus.OK)


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
@authentication_classes([])
def raise_exception(request: HttpRequest) -> typing.NoReturn:
    raise Exception("This is a test exception")
