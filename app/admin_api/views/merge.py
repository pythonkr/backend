from admin_api.filtersets.merge import UserMergeAdminFilterSet
from admin_api.serializers.merge import UserMergeHistoryAdminSerializer, UserMergeHistoryListAdminSerializer
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from django.db.models import Prefetch
from django.db.models.query import QuerySet
from django.db.transaction import atomic, set_rollback
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, mixins, request, response, status, viewsets
from rest_framework.exceptions import ValidationError
from user.models.merge import MergeError, UserMergeHistory, UserMergeObject


@extend_schema_view(
    list=extend_schema(tags=[OpenAPITag.ADMIN_USER]),
    retrieve=extend_schema(tags=[OpenAPITag.ADMIN_USER]),
    create=extend_schema(tags=[OpenAPITag.ADMIN_USER]),
)
class UserMergeAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    JsonSchemaMixin,
    SelectablesMixin,
    viewsets.GenericViewSet,
):
    pagination_class = AdminPagination
    http_method_names = ["get", "post"]
    permission_classes = [IsSuperUser]
    serializer_class = UserMergeHistoryAdminSerializer
    filterset_class = UserMergeAdminFilterSet
    queryset = UserMergeHistory.objects.select_related_with_user("source", "target").order_by("-created_at", "-id")

    def get_queryset(self) -> QuerySet:
        qs = super().get_queryset()
        return (
            qs
            if self.action == "list"
            else qs.prefetch_related(
                Prefetch(
                    lookup="merged_objects",
                    queryset=UserMergeObject.objects.select_related("target_type"),
                ),
            )
        )

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return UserMergeHistoryListAdminSerializer
        return UserMergeHistoryAdminSerializer

    @extend_schema(
        tags=[OpenAPITag.ADMIN_USER],
        request=UserMergeHistoryAdminSerializer,
        responses={status.HTTP_200_OK: UserMergeHistoryAdminSerializer},
    )
    @decorators.action(detail=False, methods=["POST"], url_path="preview")
    def preview(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with atomic():
            serializer.save()
            data = serializer.data
            set_rollback(True)
        return response.Response(data=data)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_USER],
        request=None,
        responses={status.HTTP_200_OK: UserMergeHistoryAdminSerializer},
    )
    @decorators.action(detail=True, methods=["POST"], url_path="revert")
    def revert(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        history: UserMergeHistory = self.get_object()
        try:
            history.unmerge()
        except MergeError as e:
            raise ValidationError({"detail": e.localized(en=False)}) from e

        return response.Response(data=self.get_serializer(history).data)
