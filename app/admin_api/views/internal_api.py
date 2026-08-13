from admin_api.serializers.internal_api import RegistrationDeskConfigAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from drf_spectacular.utils import extend_schema, extend_schema_view
from internal_api.models import RegistrationDeskConfig
from rest_framework import viewsets

CRUD_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_REGISTRATION_DESK]) for m in CRUD_METHODS})
class RegistrationDeskConfigAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = RegistrationDeskConfigAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_fields = ["event"]
    queryset = (
        RegistrationDeskConfig.objects.filter_active()
        .select_related_with_user("event", "event__logo")
        .prefetch_active_targets()
    )
