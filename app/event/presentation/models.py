from __future__ import annotations

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet, MarkdownField
from django.contrib.auth import get_user_model
from django.db import models
from event.models import Event
from file.models import PublicFile

User = get_user_model()


class PresentationQuerySet(BaseAbstractModelQuerySet):
    def get_all_nested_data(self):
        return self.filter_active().prefetch_related(
            models.Prefetch(
                lookup="categories",
                queryset=PresentationCategory.objects.filter_active(),
                to_attr="_prefetched_active_categories",
            ),
            models.Prefetch(
                lookup="speakers",
                queryset=PresentationSpeaker.objects.filter_active().select_related("user"),
                to_attr="_prefetched_active_speakers",
            ),
        )


class PresentationType(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "name"],
                name="uq__prst_type__event__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.event.name}] {self.name}"


class PresentationCategory(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["type", "name"],
                name="uq__prst_cat__type__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Presentation(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    title = models.CharField(max_length=256)
    summary = models.TextField(blank=True, default="")
    description = MarkdownField(blank=True, default="")
    image = models.ForeignKey(PublicFile, on_delete=models.PROTECT, null=True, blank=True)
    categories = models.ManyToManyField(to="PresentationCategory", through="PresentationCategoryRelation")

    objects: PresentationQuerySet = PresentationQuerySet.as_manager()

    def __str__(self) -> str:
        return f"[{self.type.name}] {self.title}"


class PresentationCategoryRelation(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE)
    category = models.ForeignKey(PresentationCategory, on_delete=models.CASCADE)


class PresentationSpeaker(BaseAbstractModel):
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="speakers")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    image = models.ForeignKey(PublicFile, on_delete=models.PROTECT, null=True, blank=True)
    biography = MarkdownField(blank=True, default="")
