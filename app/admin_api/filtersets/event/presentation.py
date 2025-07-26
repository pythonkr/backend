from django_filters import rest_framework as filters


class PresentationCategoryAdminFilterSet(filters.FilterSet):
    type = filters.UUIDFilter(field_name="type_id")


class PresentationAdminFilterSet(filters.FilterSet):
    type = filters.UUIDFilter(field_name="type_id")


class PresentationSpeakerAdminFilterSet(filters.FilterSet):
    presentation = filters.UUIDFilter(field_name="presentation_id")


class RoomScheduleAdminFilterSet(filters.FilterSet):
    room = filters.UUIDFilter(field_name="room_id")
    presentation = filters.UUIDFilter(field_name="presentation_id")
