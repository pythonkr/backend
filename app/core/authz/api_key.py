from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

INVALID_API_KEY_MESSAGE = "API Key가 올바르지 않습니다."


class APIKeyPermission(BasePermission):
    name: str = ""
    message = INVALID_API_KEY_MESSAGE

    def has_permission(self, request: Request, view: APIView) -> bool:
        api_key = request.headers.get("x-api-key", "")
        return api_key.lower() == self.name and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        return self.has_permission(request, view)


class RegistrationDeskAPIKeyPermission(APIKeyPermission):
    name = "registration_desk"
