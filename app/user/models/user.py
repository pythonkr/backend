from django.contrib.auth.models import AbstractUser
from django.db import models


class UserExt(AbstractUser):
    nickname = models.CharField(max_length=128, unique=True, null=True, blank=True)

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.nickname} <{self.email}>"
