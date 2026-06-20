from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar, Literal

from core.util.dateutil import now_aware
from django.conf import settings
from django.utils.functional import SimpleLazyObject
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from jwt import decode, encode
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.serializers import Serializer, UUIDField, ValidationError

if TYPE_CHECKING:
    from drf_spectacular.openapi import AutoSchema
    from user.models import UserExt


class JwtTokenSerializer(Serializer):
    ISS: ClassVar[str] = "pyconkr"
    SUB: ClassVar[str] = "jwt"
    TTL: ClassVar[timedelta] = timedelta(hours=1)

    aud = UUIDField()

    @staticmethod
    def get_queryset():
        from user.models.user import UserExt

        return UserExt.objects.filter(is_active=True)

    def validate_aud(self, value):
        if not self.get_queryset().filter(unique_id=value).exists():
            raise ValidationError("Invalid token audience.")
        return value

    def get_user(self) -> "UserExt":
        return self.get_queryset().get(unique_id=self.validated_data["aud"])

    @classmethod
    def issue(cls, user: "UserExt", *, extra_claims: dict | None = None) -> str:
        """user 에 대한 JWT 발급(HS256). `extra_claims` 로 jti 등 추가 클레임 주입(서브클래스가 재사용)."""
        now = now_aware()
        return encode(
            {
                "iss": cls.ISS,
                "sub": cls.SUB,
                "aud": str(user.unique_id),
                "iat": now,
                "exp": now + cls.TTL,
                **(extra_claims or {}),
            },
            key=settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )


class JwtBearerAuthentication(BaseAuthentication):
    JWT_SERIALIZER_CLASS: ClassVar[type[JwtTokenSerializer]] = JwtTokenSerializer

    def authenticate(self, request) -> tuple["UserExt", dict] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"bearer":
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Invalid bearer header. Expected 'Bearer <token>'.")

        try:
            payload = decode(
                jwt=header[1],
                key=settings.JWT_SECRET_KEY,
                algorithms=["HS256"],
                issuer=self.JWT_SERIALIZER_CLASS.ISS,
                subject=self.JWT_SERIALIZER_CLASS.SUB,
                options={"verify_aud": False, "require": ["exp", "iat"]},
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationFailed(detail="Token has expired.", code="token_expired") from exc
        except InvalidTokenError as exc:
            raise AuthenticationFailed(detail="Invalid token.", code="invalid_token") from exc

        serializer = self.JWT_SERIALIZER_CLASS(data=payload)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            raise AuthenticationFailed(detail=exc.detail, code="invalid_token") from exc

        return SimpleLazyObject(serializer.get_user), serializer.validated_data

    def authenticate_header(self, request) -> Literal['Bearer realm="api"']:
        return 'Bearer realm="api"'


class JwtBearerAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = JwtBearerAuthentication
    match_subclasses = True
    name = "jwtAuth"

    def get_security_definition(self, auto_schema: "AutoSchema") -> dict[str, str]:
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
