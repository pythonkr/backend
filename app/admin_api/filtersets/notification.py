from django_filters import rest_framework as filters


class NotificationTemplateAdminFilterSet(filters.FilterSet):
    code = filters.CharFilter(field_name="code", lookup_expr="icontains")
    title = filters.CharFilter(field_name="title", lookup_expr="icontains")


class NotificationHistoryAdminFilterSet(filters.FilterSet):
    template = filters.UUIDFilter(field_name="template_id")
    created_by__username = filters.CharFilter(field_name="created_by__username", lookup_expr="icontains")
