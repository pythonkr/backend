from django_filters import rest_framework as filters
from event.sponsor.models import SponsorTag


class SponsorTierAdminFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(field_name="event_id")
    name = filters.CharFilter(lookup_expr="icontains")


class SponsorTagAdminFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(field_name="event_id")
    name = filters.CharFilter(lookup_expr="icontains")


class SponsorAdminFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(field_name="event_id")
    name = filters.CharFilter(lookup_expr="icontains")
    tier = filters.BaseInFilter(field_name="tiers", distinct=True)
    tag = filters.ModelMultipleChoiceFilter(
        field_name="tags", queryset=SponsorTag.objects.filter_active(), distinct=True
    )
