import datetime
import typing

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.core.validators import MinValueValidator
from django.db import models


class Page(BaseAbstractModel):
    css = models.TextField(null=True, blank=True, default=None)
    title = models.CharField(max_length=256)
    subtitle = models.CharField(max_length=512)

    def __str__(self):
        return str(self.title)


class SitemapQuerySet(BaseAbstractModelQuerySet):
    def filter_by_today(self) -> typing.Self:
        now = datetime.datetime.now()
        return self.filter(
            models.Q(display_start_at__isnull=True) | models.Q(display_start_at__lte=now),
            models.Q(display_end_at__isnull=True) | models.Q(display_end_at__gte=now),
        )


class Sitemap(BaseAbstractModel):
    parent_sitemap = models.ForeignKey(
        "self", null=True, default=None, on_delete=models.SET_NULL, related_name="children"
    )

    name = models.CharField(max_length=256)
    order = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    page = models.ForeignKey(Page, on_delete=models.PROTECT)

    display_start_at = models.DateTimeField(null=True, blank=True)
    display_end_at = models.DateTimeField(null=True, blank=True)

    objects: SitemapQuerySet = SitemapQuerySet.as_manager()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return str(self.name)


class Section(BaseAbstractModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    order = models.IntegerField(default=0)

    css = models.TextField(null=True, blank=True, default=None)
    body = models.TextField(help_text="Content of the page, Written in markdown format")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Section {self.order} of {self.page}"
