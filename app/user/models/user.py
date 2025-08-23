from __future__ import annotations

from core.const.system import SYSTEM_EMAIL, SYSTEM_USERNAME
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserExt(AbstractUser):
    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"

    @classmethod
    def get_system_user(cls) -> UserExt:
        return cls.objects.get_or_create(username=SYSTEM_USERNAME, email=SYSTEM_EMAIL)[0]
