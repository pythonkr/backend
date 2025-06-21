from event.sponsor.models import Sponsor, SponsorTier
from rest_framework import serializers


class SponsorSerializer(serializers.ModelSerializer):
    logo = serializers.FileField(source="logo.file", read_only=True)
    tags = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Sponsor
        fields = ("id", "name", "logo", "description", "tags")


class SponsorTierSerializer(serializers.ModelSerializer):
    sponsors = SponsorSerializer(source="active_sponsors", many=True, read_only=True)

    class Meta:
        model = SponsorTier
        fields = ("id", "name", "order", "sponsors")
