from django.contrib.auth.models import AbstractUser
from django.db import models


class UserExt(AbstractUser):
    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"
