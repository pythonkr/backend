from event.sponsor.models import Sponsor
from event.sponsor.serializers import SponsorSerializer
from rest_framework import mixins, viewsets


class SponsorViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Sponsor.objects.prefetch_related("sponsor_tier").filter_active()
    serializer_class = SponsorSerializer
