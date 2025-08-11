import collections.abc
import contextlib
import functools

from core.models import BaseAbstractModel, MarkdownField
from django.db import models
from event.models import Event


class Sponsor(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    logo = models.ForeignKey(to="file.PublicFile", on_delete=models.PROTECT)
    description = MarkdownField(blank=True, default="")

    tiers = models.ManyToManyField(to="SponsorTier", through="SponsorTierSponsorRelation")
    tags = models.ManyToManyField(to="SponsorTag", through="SponsorTagRelation")
    fixed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["fixed_at", "name"]
        indexes = [models.Index(fields=["event", "fixed_at"], name="idx__spsr__event_fixed_at")]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "name"],
                name="uq__spsr__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event.name} - {self.name}"


class SponsorTier(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)
    order = models.IntegerField(default=0)

    sponsors = models.ManyToManyField(to=Sponsor, through="SponsorTierSponsorRelation")

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "name"],
                name="uq__spsr_tier__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["event", "order"],
                name="uq__spsr_tier__order",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event.name} - {self.name}"

    @functools.cached_property
    def active_sponsors(self) -> collections.abc.Iterable[Sponsor]:
        with contextlib.suppress(AttributeError):
            return self._prefetched_active_sponsors

        return self.sponsors.filter_active().select_related("logo")


class SponsorTierSponsorRelation(models.Model):
    tier = models.ForeignKey(SponsorTier, on_delete=models.CASCADE)
    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tier", "sponsor"], name="uq__spsr_tier_rel__tier_spsr")]


class SponsorTag(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="uq__spsr_tag__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SponsorTagRelation(models.Model):
    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE)
    tag = models.ForeignKey(SponsorTag, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sponsor", "tag"], name="uq__spsr_tag_rel__spsr_tag")]
