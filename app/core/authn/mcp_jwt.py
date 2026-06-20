"""MCP 전용 JWT 인증 — JwtBearerAuthentication 상속, 시리얼라이저만 교체.

MCP JWT 는 `sub="mcp"` 라 base(subject="jwt") 로는 거부되고 오직 McpJwtAuthentication 으로만
인증된다 → 매 요청 jti(McpToken) 검사가 항상 적용돼, TTL 과 무관하게 즉시 폐기 가능(PAT 형).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

from core.authn.jwt_authn import JwtBearerAuthentication, JwtTokenSerializer
from core.util.dateutil import now_aware
from django.conf import settings
from jwt import encode
from rest_framework.serializers import UUIDField, ValidationError

if TYPE_CHECKING:
    from user.models import UserExt
    from user.models.mcp_token import McpToken


class McpJwtTokenSerializer(JwtTokenSerializer):
    SUB: ClassVar[str] = "mcp"
    TTL: ClassVar[timedelta] = timedelta(days=3650)

    jti = UUIDField()

    def validate(self, attrs: dict) -> dict:
        from user.models.mcp_token import McpToken

        token = (
            McpToken.objects.filter_active()
            .select_related("user")
            .filter(id=attrs["jti"], user__unique_id=attrs["aud"], user__is_active=True)
            .first()
        )
        if token is None:
            raise ValidationError("Invalid or revoked MCP token.")
        token.touch()
        self._user = token.user
        return attrs

    def validate_aud(self, value):
        return value  # 실제 검증은 validate(jti 기준) — base 의 중복 user 조회 제거

    def get_user(self) -> "UserExt":
        return self._user

    @classmethod
    def issue_for(cls, token: "McpToken") -> str:
        now = now_aware()
        return encode(
            {
                "iss": cls.ISS,
                "sub": cls.SUB,
                "aud": str(token.user.unique_id),
                "jti": str(token.id),
                "iat": now,
                "exp": now + cls.TTL,
            },
            key=settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )


class McpJwtAuthentication(JwtBearerAuthentication):
    JWT_SERIALIZER_CLASS = McpJwtTokenSerializer
