from admin_api.serializers.mcp_token import McpTokenAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from user.models.mcp_token import McpToken

ADMIN_METHODS = ["list", "retrieve", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_MCP_TOKEN]) for m in ADMIN_METHODS})
class McpTokenAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    JsonSchemaMixin,
    SelectablesMixin,
    viewsets.GenericViewSet,
):
    pagination_class = AdminPagination
    http_method_names = ["get", "delete"]
    serializer_class = McpTokenAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_fields = ["user"]
    queryset = McpToken.objects.filter_active().select_related_with_user("user").order_by("-created_at", "pk")
