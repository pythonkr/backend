from core.const.tag import OpenAPITag
from django.db import models
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from event.sponsor.models import Sponsor, SponsorTier
from event.sponsor.serializers import SponsorTierSerializer
from rest_framework import mixins, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_SPONSOR]))
class SponsorTierViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = SponsorTier.objects.filter_active().prefetch_related(
        models.Prefetch(
            lookup="sponsors",
            queryset=Sponsor.objects.filter_active().select_related("logo"),
            to_attr="_prefetched_active_sponsors",
        )
    )
    serializer_class = SponsorTierSerializer
