from django_filters import rest_framework as filters


class PresentationTypeAdminFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(field_name="event_id")
    name = filters.CharFilter(lookup_expr="icontains")


class RoomAdminFilterSet(filters.FilterSet):
    event = filters.UUIDFilter(field_name="event_id")
    name = filters.CharFilter(lookup_expr="icontains")


class PresentationCategoryAdminFilterSet(filters.FilterSet):
    type = filters.UUIDFilter(field_name="type_id")


class PresentationAdminFilterSet(filters.FilterSet):
    type = filters.UUIDFilter(field_name="type_id")


class PresentationSpeakerAdminFilterSet(filters.FilterSet):
    presentation = filters.UUIDFilter(field_name="presentation_id")


class RoomScheduleAdminFilterSet(filters.FilterSet):
    room = filters.UUIDFilter(field_name="room_id")
    presentation = filters.UUIDFilter(field_name="presentation_id")
