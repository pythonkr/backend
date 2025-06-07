from core.models import BaseAbstractModel
from django.db import models
from event.models import Event


class Sponsor(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="sponsors")
    name = models.CharField(max_length=256, null=True, blank=True)
    logo = models.URLField(null=True, blank=True)
    description = models.CharField(max_length=1000, null=True, blank=True)
    sponsor_tiers = models.ManyToManyField(to="SponsorTier", through="SponsorTierSponsorRelation")


class SponsorTier(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="sponsor_tiers")
    name = models.CharField(max_length=256, null=True, blank=True)
    order = models.IntegerField(null=True, blank=True)


class SponsorTierSponsorRelation(models.Model):
    sponsor_tier = models.ForeignKey(
        SponsorTier, on_delete=models.CASCADE, related_name="sponsor_tier_sponsor_relations"
    )
    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="sponsor_tier_sponsor_relations")
