from admin_api.filtersets.document import IssuedDocumentAdminFilterSet
from admin_api.serializers.document import DocumentTemplateAdminSerializer, IssuedDocumentAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from document.models import DocumentTemplate, IssuedDocument
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import request, response
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

TEMPLATE_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
ISSUED_METHODS = ["list", "retrieve", "revoke"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_DOCUMENT]) for m in TEMPLATE_METHODS})
class DocumentTemplateAdminViewSet(JsonSchemaViewSet, ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    permission_classes = [IsSuperUser]
    serializer_class = DocumentTemplateAdminSerializer
    queryset = DocumentTemplate.objects.filter_active().select_related_with_user().order_by("-created_at", "pk")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_DOCUMENT]) for m in ISSUED_METHODS})
class IssuedDocumentAdminViewSet(JsonSchemaViewSet, ReadOnlyModelViewSet):
    permission_classes = [IsSuperUser]
    filterset_class = IssuedDocumentAdminFilterSet
    serializer_class = IssuedDocumentAdminSerializer
    queryset = (
        IssuedDocument.objects.filter_active()
        .select_related_with_user("template", "revoked_by")
        .prefetch_related("issuable")
        .order_by("-created_at", "pk")
    )

    @extend_schema(request=None, responses={200: IssuedDocumentAdminSerializer})
    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        document: IssuedDocument = self.get_object()
        if document.revoked_at is None:
            document.revoke()
        return response.Response(data=self.get_serializer(instance=document).data)
