from event.sponsor.models import Sponsor, SponsorTier
from rest_framework import serializers


class SponsorTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = SponsorTier
        fields = (
            "id",
            "name",
            "order",
        )


class SponsorSerializer(serializers.ModelSerializer):
    sponsor_tiers = SponsorTierSerializer(many=True, read_only=True, source="sponsor_tier")

    class Meta:
        model = Sponsor
        fields = (
            "id",
            "event",
            "name",
            "logo",
            "description",
            "sponsor_tiers",
        )
