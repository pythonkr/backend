from __future__ import annotations

import typing
from uuid import uuid4

from core.const.system import SYSTEM_EMAIL, SYSTEM_USERNAME
from core.scancode_mixin import ScanCodeMixin
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserExt(ScanCodeMixin, AbstractUser):
    scancode_prefix = "user"
    scancode_uuid_field = "unique_id"

    choices_meta_schema: typing.ClassVar[dict] = {
        "email": {"label": "이메일", "type": "string", "filter": "search"},
        "nickname": {"label": "닉네임", "type": "string", "filter": "search"},
        "is_active": {"label": "활성", "type": "boolean"},
        "is_superuser": {"label": "스태프", "type": "boolean"},
    }

    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    unique_id = models.UUIDField(unique=True, editable=False, null=False, blank=False, default=uuid4)

    class Meta(AbstractUser.Meta):
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["unique_id"], name="userext_unique_id_idx")]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"

    def get_choice_meta(self) -> dict:
        return {
            "email": self.email,
            "nickname": self.nickname,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
        }

    @classmethod
    def get_system_user(cls) -> UserExt:
        return cls.objects.get_or_create(username=SYSTEM_USERNAME, email=SYSTEM_EMAIL)[0]
