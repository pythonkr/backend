from __future__ import annotations

import contextlib
import importlib
import threading
import typing

from core.const.system import SYSTEM_ID
from django.http.request import HttpRequest

if typing.TYPE_CHECKING:
    from user.models import UserExt

thread_local = threading.local()


def get_request() -> HttpRequest | None:
    with contextlib.suppress(AttributeError):
        return thread_local.current_request
    return None


def get_current_user() -> "UserExt" | None:
    if (request := get_request()) and hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
        return request.user

    if UserExt := getattr(importlib.import_module("user.models"), "UserExt", None):
        return UserExt.objects.filter(id=SYSTEM_ID).first()

    return None
