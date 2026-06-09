from django_filters import rest_framework as filters
from document.models import DocumentType


class IssuedDocumentAdminFilterSet(filters.FilterSet):
    template = filters.UUIDFilter(field_name="template_id")
    document_type = filters.MultipleChoiceFilter(field_name="template__document_type", choices=DocumentType.choices)
    is_revoked = filters.BooleanFilter(field_name="revoked_at", lookup_expr="isnull", exclude=True)
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
