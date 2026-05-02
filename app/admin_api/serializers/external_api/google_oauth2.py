from logging import getLogger

from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.util.google_api import fetch_access_token, fetch_token_info
from external_api.google_oauth2.models import GoogleOAuth2
from httpx import HTTPError
from rest_framework import serializers

logger = getLogger(__name__)


class GoogleOAuth2AdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = GoogleOAuth2
        fields = COMMON_ADMIN_FIELDS + ("refresh_token",)

    def validate_refresh_token(self, value: str) -> str:
        if self.instance and self.instance.refresh_token == value:
            return value
        try:
            fetch_access_token(value)
        except HTTPError as e:
            raise serializers.ValidationError(f"Refresh token is invalid: {e}") from e
        return value


class GoogleOAuth2AdminAccessTokenSerializer(serializers.Serializer):
    is_valid = serializers.BooleanField(read_only=True, default=False)
    access_token = serializers.CharField(read_only=True, allow_null=True, allow_blank=True, default=None)
    token_type = serializers.CharField(read_only=True, allow_null=True, allow_blank=True, default=None)
    expires_in = serializers.IntegerField(read_only=True, allow_null=True, default=None)
    scopes = serializers.ListField(child=serializers.CharField(), read_only=True, default=list)
    email = serializers.CharField(read_only=True, allow_null=True, allow_blank=True, default=None)
    audience = serializers.CharField(read_only=True, allow_null=True, allow_blank=True, default=None, source="aud")
    error = serializers.CharField(read_only=True, allow_null=True, allow_blank=True, default=None)

    def to_representation(self, instance: GoogleOAuth2) -> dict:
        try:
            token_payload = fetch_access_token(instance.refresh_token)
        except HTTPError as e:
            logger.warning("Failed to refresh Google OAuth2 access token: %s", e)
            return super().to_representation({"error": str(e)})

        try:
            token_info = fetch_token_info(token_payload["access_token"])
        except HTTPError as e:
            # str(e)에는 query string의 access_token이 그대로 포함되므로 redact 후 로깅.
            redacted = str(e).replace(token_payload["access_token"], "[REDACTED]")
            logger.warning("Failed to fetch Google OAuth2 token info: %s", redacted)
            token_info = {}

        merged = token_payload | token_info
        return super().to_representation(merged | {"is_valid": True, "scopes": (merged.get("scope") or "").split()})
