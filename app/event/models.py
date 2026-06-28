import typing

from core.models import BaseAbstractModel
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from file.models import PublicFile
from user.models.organization import Organization


class Event(BaseAbstractModel):
    choices_select_related = ("organization",)
    choices_meta_schema: typing.ClassVar[dict] = {
        "organization": {"label": "조직", "type": "string", "filter": "select"},
        "started_at": {"label": "시작일", "type": "string", "filter": "search"},
    }

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="events")
    name = models.CharField(max_length=256)
    logo = models.ForeignKey(PublicFile, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    banner_image = models.TextField(null=True, blank=True)
    slogan = models.CharField(max_length=1000, null=True, blank=True)
    description = models.CharField(max_length=1000, null=True, blank=True)
    event_start_at = models.DateTimeField(null=True, blank=True)
    event_end_at = models.DateTimeField(null=True, blank=True)
    banner_display_start_at = models.DateTimeField(null=True, blank=True)
    banner_display_end_at = models.DateTimeField(null=True, blank=True)
    stats_start_date = models.DateField(null=True, blank=True)
    stats_end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-event_start_at", "-event_end_at"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq__evt__name", condition=models.Q(deleted_at__isnull=True))
        ]

    def __str__(self):
        return f"{self.name} by {self.organization}"

    def _choice_meta_fields(self) -> dict:
        return {
            "organization": str(self.organization),
            "started_at": timezone.localtime(self.event_start_at).date().isoformat() if self.event_start_at else None,
        }

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
        if self.stats_start_date and self.stats_end_date and self.stats_start_date > self.stats_end_date:
            raise ValidationError("통계 종료일은 시작일보다 이전일 수 없습니다.")
