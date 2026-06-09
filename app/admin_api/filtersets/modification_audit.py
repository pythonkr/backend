from django_filters import rest_framework as filters
from participant_portal_api.models import ModificationAudit


class ModificationAuditAdminFilterSet(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=ModificationAudit.Status.choices)
    action = filters.MultipleChoiceFilter(choices=ModificationAudit.Action.choices)
    instance_type = filters.CharFilter(field_name="instance_type__model", lookup_expr="iexact")
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
