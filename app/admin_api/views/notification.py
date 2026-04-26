from __future__ import annotations

from contextlib import suppress

from admin_api.filtersets.notification import NotificationHistoryAdminFilterSet, NotificationTemplateAdminFilterSet
from admin_api.serializers.notification import (
    EmailNotificationTemplateAdminSerializer,
    NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer,
    NHNCloudSMSNotificationTemplateAdminSerializer,
    NotificationHistoryAdminSerializer,
    NotificationHistoryCreateRequestAdminSerializer,
    NotificationTemplateRenderRequestAdminSerializer,
)
from core.const.tag import OpenAPITag
from core.openapi.schemas import build_html_responses
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from notification.models import (
    EmailNotificationHistory,
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationHistory,
    NHNCloudKakaoAlimTalkNotificationTemplate,
    NHNCloudSMSNotificationHistory,
    NHNCloudSMSNotificationTemplate,
)
from notification.models.base import NotificationHistoryBase, NotificationStatus
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

TEMPLATE_READ_METHODS = ["list", "retrieve", "render_preview", "create_history"]
TEMPLATE_CRUD_METHODS = TEMPLATE_READ_METHODS + ["create", "update", "partial_update", "destroy"]
HISTORY_METHODS = ["list", "retrieve", "partial_update", "retry"]


class _NotiTemplateAdminActionMixin(JsonSchemaViewSet):
    permission_classes = [IsSuperUser]
    filterset_class = NotificationTemplateAdminFilterSet

    @extend_schema(
        request=NotificationTemplateRenderRequestAdminSerializer,
        responses=build_html_responses(names=["Notification Template Render Preview"]),
    )
    # @action 에서 serializer_class를 override하지 않음 — get_serializer()가 viewset의 template serializer를
    # 그대로 반환해야 instance 메서드(render/create_history) 사용 가능. 요청 body 스키마는 위 @extend_schema에서 명시.
    @action(detail=True, methods=["post"], url_path="render", renderer_classes=[StaticHTMLRenderer])
    def render_preview(self, request: Request, *args: tuple, **kwargs: dict) -> Response:
        request_serializer = NotificationTemplateRenderRequestAdminSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        template_serializer = self.get_serializer(instance=self.get_object())
        return Response(data=template_serializer.render(request_serializer.validated_data["context"]))

    @extend_schema(
        request=NotificationHistoryCreateRequestAdminSerializer,
        responses={HTTP_201_CREATED: NotificationHistoryAdminSerializer},
    )
    @action(detail=True, methods=["post"], url_path="history")
    def create_history(self, request: Request, *args: tuple, **kwargs: dict) -> Response:
        request_serializer = NotificationHistoryCreateRequestAdminSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        template_serializer = self.get_serializer(instance=self.get_object())
        history = template_serializer.create_history(**request_serializer.validated_data)
        return Response(data=NotificationHistoryAdminSerializer(instance=history).data, status=HTTP_201_CREATED)


class _NotiHistoryAdminViewSetBase(ListModelMixin, RetrieveModelMixin, UpdateModelMixin, JsonSchemaViewSet):
    http_method_names = ["get", "patch", "post"]
    permission_classes = [IsSuperUser]
    filterset_class = NotificationHistoryAdminFilterSet
    serializer_class = NotificationHistoryAdminSerializer

    @extend_schema(responses={HTTP_200_OK: NotificationHistoryAdminSerializer})
    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, *args: tuple, **kwargs: dict) -> Response:
        history: NotificationHistoryBase = self.get_object()
        if history.status != NotificationStatus.FAILED:
            raise ValidationError(f"재시도는 FAILED 상태에서만 가능합니다. (현재: {history.status})")

        with suppress(Exception):
            history.send()

        return Response(data=self.get_serializer(history).data)


# ---- Template -----------------------------------------------------------


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_EMAIL]) for m in TEMPLATE_CRUD_METHODS})
class EmailNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = EmailNotificationTemplateAdminSerializer
    queryset = EmailNotificationTemplate.objects.filter_active().select_related_with_user()


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_KAKAO_ALIMTALK]) for m in TEMPLATE_READ_METHODS})
class NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ReadOnlyModelViewSet):
    serializer_class = NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer
    queryset = NHNCloudKakaoAlimTalkNotificationTemplate.objects.filter_active().select_related_with_user()


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_SMS]) for m in TEMPLATE_CRUD_METHODS})
class NHNCloudSMSNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = NHNCloudSMSNotificationTemplateAdminSerializer
    queryset = NHNCloudSMSNotificationTemplate.objects.filter_active().select_related_with_user()


# ---- History ----------------------------------------------------------------


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_EMAIL]) for m in HISTORY_METHODS})
class EmailNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    queryset = EmailNotificationHistory.objects.filter_active().select_related_with_user("template")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_KAKAO_ALIMTALK]) for m in HISTORY_METHODS})
class NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    queryset = NHNCloudKakaoAlimTalkNotificationHistory.objects.filter_active().select_related_with_user("template")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_SMS]) for m in HISTORY_METHODS})
class NHNCloudSMSNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    queryset = NHNCloudSMSNotificationHistory.objects.filter_active().select_related_with_user("template")
