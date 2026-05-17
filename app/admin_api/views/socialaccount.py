from admin_api.filtersets.socialaccount import EmailAddressAdminFilterSet, SocialAccountAdminFilterSet
from admin_api.serializers.socialaccount import (
    EmailAddressAdminSerializer,
    SocialAccountAdminSerializer,
    SocialAppAdminSerializer,
)
from admin_api.services.socialaccount import delete_social_accounts_and_cleanup_user_emails
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets

DESTROY_ONLY_METHODS = ["list", "retrieve", "destroy"]
ADMIN_METHODS = DESTROY_ONLY_METHODS + ["create", "partial_update"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_ALLAUTH]) for m in ADMIN_METHODS})
class SocialAppAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    permission_classes = [IsSuperUser]
    pagination_class = AdminPagination
    serializer_class = SocialAppAdminSerializer
    queryset = SocialApp.objects.all().order_by("provider", "id")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_ALLAUTH]) for m in DESTROY_ONLY_METHODS})
class SocialAccountAdminViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    JsonSchemaViewSet,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "delete"]
    permission_classes = [IsSuperUser]
    pagination_class = AdminPagination
    serializer_class = SocialAccountAdminSerializer
    queryset = SocialAccount.objects.all().select_related("user").order_by("-date_joined", "-id")
    filterset_class = SocialAccountAdminFilterSet

    def perform_destroy(self, instance: SocialAccount) -> None:
        delete_social_accounts_and_cleanup_user_emails(SocialAccount.objects.filter(pk=instance.pk))


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_ALLAUTH]) for m in ADMIN_METHODS})
class EmailAddressAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = EmailAddressAdminSerializer
    permission_classes = [IsSuperUser]
    pagination_class = AdminPagination
    queryset = EmailAddress.objects.all().select_related("user").order_by("-id")
    filterset_class = EmailAddressAdminFilterSet
