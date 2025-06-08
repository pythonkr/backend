from __future__ import annotations

import collections.abc
import contextlib
import functools

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.contrib.auth import get_user_model
from django.db import models
from event.models import Event

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
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="uq__prst_type__event__name")]

    def __str__(self) -> str:
        return f"[{self.event.name}] {self.name}"


class PresentationCategory(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["type", "name"], name="uq__prst_cat__type__name")]

    def __str__(self) -> str:
        return self.name


class Presentation(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    title = models.CharField(max_length=256)
    sitemap = models.ForeignKey(to="cms.Sitemap", on_delete=models.PROTECT, null=True, blank=True)

    categories = models.ManyToManyField(to="PresentationCategory", through="PresentationCategoryRelation")

    objects: PresentationQuerySet = PresentationQuerySet.as_manager()

    def __str__(self) -> str:
        return f"[{self.type.name}] {self.title}"

    @functools.cached_property
    def active_categories(self) -> collections.abc.Iterable[PresentationCategory]:
        with contextlib.suppress(AttributeError):
            return self._prefetched_active_categories

        return self.categories.filter_active()

    @functools.cached_property
    def active_speakers(self) -> collections.abc.Iterable[PresentationSpeaker]:
        with contextlib.suppress(AttributeError):
            return self._prefetched_active_speakers

        return self.speakers.filter_active().select_related("user")


class PresentationCategoryRelation(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE)
    category = models.ForeignKey(PresentationCategory, on_delete=models.CASCADE)


class PresentationSpeaker(BaseAbstractModel):
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="speakers")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    biography = models.TextField(blank=True, default="")
