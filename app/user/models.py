from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class UserExt(AbstractUser):
    pass


from core.models import BaseAbstractModel  # noqa: E402


class Organization(BaseAbstractModel):
    name = models.CharField(max_length=256, null=True, blank=True)


class OrganizationUserRelation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="organization_user_relations")
    user = models.ForeignKey(UserExt, on_delete=models.PROTECT, related_name="organization_user_relations")
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    def clean(self) -> None:
        super().clean()
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise ValidationError("종료 날짜는 시작 날짜보다 이전일 수 없습니다.")
