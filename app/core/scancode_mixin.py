from __future__ import annotations

from base64 import urlsafe_b64encode
from contextlib import suppress
from functools import cached_property
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from typing import ClassVar, Self
from uuid import UUID

from django.conf import settings
from rest_framework.reverse import reverse
from shortuuid import decode, encode


class ScanCodeMixin:
    scancode_prefix: ClassVar[str]
    scancode_uuid_field: ClassVar[str] = "id"

    @property
    def _scancode_uuid(self) -> UUID:
        return getattr(self, self.scancode_uuid_field)

    @cached_property
    def short_id(self) -> str:
        return encode(self._scancode_uuid)

    def _salt_with(self, secret: str) -> str:
        hmac_result = hmac_new(secret.encode(), self._scancode_uuid.bytes, sha256).digest()
        return urlsafe_b64encode(hmac_result).decode("utf-8").rstrip("=")

    @cached_property
    def salt(self) -> str:
        return self._salt_with(settings.SHOP.order_scancode_salts[0])

    def verify_salt(self, salt: str) -> bool:
        # rotation 중에는 과거 salt 로 발급된 토큰도 받아준다.
        return any(compare_digest(self._salt_with(secret), salt) for secret in settings.SHOP.order_scancode_salts)

    @cached_property
    def scancode_token(self) -> str:
        return f"{self.scancode_prefix}:{self.short_id}:{self.salt}"

    @cached_property
    def scancode_path(self) -> str:
        return f"{reverse('v1:scancode-list')}?token={self.scancode_token}"

    @classmethod
    def from_short_id(cls, short_id: str) -> Self | None:
        with suppress(ValueError):
            queryset = cls.objects.filter_active() if hasattr(cls.objects, "filter_active") else cls.objects
            return queryset.filter(**{cls.scancode_uuid_field: decode(short_id)}).first()
        return None

    @classmethod
    def from_scancode_token(cls, scancode_token: str) -> Self | None:
        parts = scancode_token.split(":")
        if len(parts) != 3:
            return None
        prefix, short_id, salt = parts
        if prefix != cls.scancode_prefix or not (short_id and salt):
            return None
        if (instance := cls.from_short_id(short_id)) and instance.verify_salt(salt):
            return instance
        return None
