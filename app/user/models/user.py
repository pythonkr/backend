from __future__ import annotations

from uuid import uuid4

from core.const.system import SYSTEM_EMAIL, SYSTEM_USERNAME
from core.scancode_mixin import ScanCodeMixin
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserExt(ScanCodeMixin, AbstractUser):
    scancode_prefix = "user"
    scancode_uuid_field = "unique_id"

    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    unique_id = models.UUIDField(unique=True, editable=False, null=False, blank=False, default=uuid4)

    class Meta(AbstractUser.Meta):
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["unique_id"], name="userext_unique_id_idx")]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"

    @classmethod
    def get_system_user(cls) -> UserExt:
        return cls.objects.get_or_create(username=SYSTEM_USERNAME, email=SYSTEM_EMAIL)[0]
