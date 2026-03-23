from event.filters import EventFilterMixin


class SponsorTierFilterSet(EventFilterMixin):
    event_field_prefix = "event"
