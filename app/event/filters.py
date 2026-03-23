from django.db.models import Q
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES
from event.models import Event


class EventFilterMixin(filters.FilterSet):
    event = filters.CharFilter(method="filter_by_event_name")
    event_field_prefix = "event"

    def filter_by_event_name(self, queryset, name, value):
        if value in EMPTY_VALUES:
            return queryset

        prefix = self.event_field_prefix
        return queryset.filter(Q(**{f"{prefix}__name_ko": value}) | Q(**{f"{prefix}__name_en": value}))

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        if self.data.get("event") in EMPTY_VALUES:
            latest = Event.objects.filter_active().first()
            if latest:
                queryset = queryset.filter(**{self.event_field_prefix: latest})

        return queryset
