from django.contrib.auth.models import AbstractUser


class UserExt(AbstractUser):
    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.username} <{self.email}>"
