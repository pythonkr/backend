from contextlib import suppress
from typing import Literal

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

_BOOL_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_SAME_SITE_VALUES = frozenset({"lax", "strict", "none"})
_RESPONSE_BODY = """\
<!doctype html>
<html>
<head>
  <meta charset=utf-8>
  <title>Synced</title>
</head>
<body>
  <h2>.pycon.kr scope cookie sync complete</h2>
  <p>You can close this tab and proceed with the social login.</p>
</body>
</html>"""


def _parse_int(s: str | None) -> int | None:
    with suppress(ValueError):
        return int(s.strip())
    return None


def _parse_bool(s: str | None) -> bool:
    return s.strip().lower() in _BOOL_TRUE_VALUES if s else None


def _parse_samesite(s: str | None) -> Literal["Lax", "Strict", "None"] | None:
    if not s:
        return None

    s = s.strip().lower()
    return s.capitalize() if s in _SAME_SITE_VALUES else None


@csrf_exempt
@require_http_methods(["POST"])
def dev_set_cookie(request: HttpRequest) -> HttpResponse:
    if not (name := request.POST.get("name", "").strip()):
        return HttpResponseBadRequest("name required")
    if not (value := request.POST.get("value", "").strip()):
        return HttpResponseBadRequest("value required")

    response = HttpResponse(_RESPONSE_BODY, content_type="text/html; charset=utf-8")
    response.set_cookie(
        name,
        value,
        max_age=_parse_int(request.POST.get("max_age")),
        domain=request.POST.get("domain", "").strip() or None,
        secure=_parse_bool(request.POST.get("secure")),
        httponly=_parse_bool(request.POST.get("httponly")),
        samesite=_parse_samesite(request.POST.get("samesite")),
    )
    return response
