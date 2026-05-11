from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import make_password
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

if TYPE_CHECKING:
    from user.models import UserExt


class APIKeyAuthentication(BaseAuthentication):
    @staticmethod
    def _get_or_create_api_key_user(api_key: str) -> "UserExt":
        from user.models import UserExt

        username = f"API_KEY_USER_{api_key.upper()}"
        email = f"api_key_user_{api_key.lower()}@pycon.kr"

        return UserExt.objects.get_or_create(
            username=username,
            defaults={"email": email, "password": make_password(None)},
        )[0]

    def authenticate(self, request: Request) -> tuple["UserExt", None] | None:
        api_key = request.headers.get("x-api-key", "")
        api_secret = request.headers.get("x-api-secret", "")

        if api_key.lower() in settings.EXT_API_KEYS and api_secret == settings.EXT_API_KEYS.get(api_key.lower()):
            return self._get_or_create_api_key_user(api_key), None

        return None


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = APIKeyAuthentication
    name: list[str] = ["API Key", "API Secret"]

    def get_security_definition(self, auto_schema: AutoSchema) -> list[dict[str, str]]:
        return [
            {"type": "apiKey", "in": "header", "name": "x-api-key"},
            {"type": "apiKey", "in": "header", "name": "x-api-secret"},
        ]
