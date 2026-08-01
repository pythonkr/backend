from core.const.tag import OpenAPITag
from core.viewset.list_only_filter_viewset import ListOnlyFilterMixin
from django.db import models
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from event.sponsor.filters import SponsorTierFilterSet
from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
from event.sponsor.serializers import SponsorTierSerializer
from rest_framework import mixins, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_SPONSOR]))
class SponsorTierViewSet(ListOnlyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = SponsorTier.objects.filter_active().prefetch_related(
        models.Prefetch(
            lookup="sponsors",
            queryset=Sponsor.objects.filter_active()
            .select_related("logo")
            .prefetch_related(models.Prefetch(lookup="tags", queryset=SponsorTag.objects.filter_active())),
            to_attr="_prefetched_active_sponsors",
        )
    )
    serializer_class = SponsorTierSerializer
    filterset_class = SponsorTierFilterSet
