from core.models import BaseAbstractModel
from django.core.exceptions import ValidationError
from django.db import models
from user.models.organization import Organization


class Event(BaseAbstractModel):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="events")
    name = models.CharField(max_length=256)
    banner_image = models.TextField(null=True, blank=True)
    slogan = models.CharField(max_length=1000, null=True, blank=True)
    description = models.CharField(max_length=1000, null=True, blank=True)
    event_start_at = models.DateTimeField(null=True, blank=True)
    event_end_at = models.DateTimeField(null=True, blank=True)
    banner_display_start_at = models.DateTimeField(null=True, blank=True)
    banner_display_end_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-event_start_at", "-event_end_at"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq__evt__name", condition=models.Q(deleted_at__isnull=True))
        ]

    def __str__(self):
        return f"{self.name} by {self.organization}"

    def clean(self) -> None:
        super().clean()
        if self.event_start_at and self.event_end_at and self.event_start_at > self.event_end_at:
            raise ValidationError("event의 종료 날짜는 시작 날짜보다 이전일 수 없습니다.")
        if (
            self.banner_display_start_at
            and self.banner_display_end_at
            and self.banner_display_start_at > self.banner_display_end_at
        ):
            raise ValidationError("banner 전시 종료 날짜는 시작 날짜보다 이전일 수 없습니다.")
