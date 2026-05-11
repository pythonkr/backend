from __future__ import annotations

from admin_api.filtersets.notification import NotificationHistoryAdminFilterSet, NotificationTemplateAdminFilterSet
from admin_api.serializers.notification import (
    EmailNotificationHistoryAdminSerializer,
    EmailNotificationTemplateAdminSerializer,
    NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer,
    NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer,
    NHNCloudSMSNotificationHistoryAdminSerializer,
    NHNCloudSMSNotificationTemplateAdminSerializer,
    NotificationHistoryRetryRequestAdminSerializer,
    NotificationTemplateRenderRequestAdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.openapi.schemas import build_html_responses
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
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

TEMPLATE_READ_METHODS = ["list", "retrieve", "render_preview"]
TEMPLATE_CRUD_METHODS = TEMPLATE_READ_METHODS + ["create", "update", "partial_update", "destroy"]
HISTORY_METHODS = ["list", "retrieve", "create", "retry", "retry_sent_to", "render_sent_to_as_html"]


# ---- Template -----------------------------------------------------------


class _NotiTemplateAdminActionMixin(JsonSchemaViewSet):
    permission_classes = [IsSuperUser]
    filterset_class = NotificationTemplateAdminFilterSet

    @extend_schema(
        request=NotificationTemplateRenderRequestAdminSerializer,
        responses=build_html_responses(names=["Notification Template Render Preview"]),
    )
    # @action 에서 serializer_class를 override하지 않음 — get_serializer()가 viewset의 template serializer를
    # 그대로 반환해야 instance 메서드(render) 사용 가능. 요청 body 스키마는 위 @extend_schema에서 명시.
    @action(detail=True, methods=["post"], url_path="render", renderer_classes=[StaticHTMLRenderer])
    def render_preview(self, request: Request, *args: tuple, **kwargs: dict) -> Response:
        request_serializer = NotificationTemplateRenderRequestAdminSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        template_serializer = self.get_serializer(instance=self.get_object())
        return Response(data=template_serializer.render(request_serializer.validated_data["context"]))


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_EMAIL]) for m in TEMPLATE_CRUD_METHODS})
class EmailNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = EmailNotificationTemplateAdminSerializer
    queryset = EmailNotificationTemplate.objects.filter_active().select_related_with_user()


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_KAKAO_ALIMTALK]) for m in TEMPLATE_READ_METHODS})
class NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ReadOnlyModelViewSet):
    serializer_class = NHNCloudKakaoAlimTalkNotificationTemplateAdminSerializer
    queryset = NHNCloudKakaoAlimTalkNotificationTemplate.objects.filter_active().select_related_with_user()

    def get_queryset(self):
        if self.action in TEMPLATE_READ_METHODS:
            NHNCloudKakaoAlimTalkNotificationTemplate.objects.sync_with_nhn_cloud()
        return super().get_queryset()


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_SMS]) for m in TEMPLATE_CRUD_METHODS})
class NHNCloudSMSNotificationTemplateAdminViewSet(_NotiTemplateAdminActionMixin, ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = NHNCloudSMSNotificationTemplateAdminSerializer
    queryset = NHNCloudSMSNotificationTemplate.objects.filter_active().select_related_with_user()


# ---- History ----------------------------------------------------------------


class _NotiHistoryAdminViewSetBase(CreateModelMixin, ListModelMixin, RetrieveModelMixin, JsonSchemaViewSet):
    permission_classes = [IsSuperUser]
    filterset_class = NotificationHistoryAdminFilterSet

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request: Request, *args: tuple, **kwargs: dict) -> Response:
        query = NotificationHistoryRetryRequestAdminSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        serializer = self.get_serializer(instance=self.get_object())
        serializer.retry(statuses=query.validated_data["status"])
        return Response(data=serializer.data)

    @action(detail=True, methods=["post"], url_path=r"sent-to/(?P<sent_to_id>[^/.]+)/retry")
    def retry_sent_to(self, request: Request, sent_to_id: str, *args: tuple, **kwargs: dict) -> Response:
        query = NotificationHistoryRetryRequestAdminSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        history = self.get_object()
        get_object_or_404(history.sent_to_list.all(), pk=sent_to_id, status__in=query.validated_data["status"])
        serializer = self.get_serializer(instance=history)
        serializer.retry(statuses=query.validated_data["status"], sent_to_id=sent_to_id)
        return Response(data=serializer.data)

    @extend_schema(responses=build_html_responses(names=["Notification History SentTo Render As HTML"]))
    @action(
        detail=True,
        methods=["get"],
        url_path=r"sent-to/(?P<sent_to_id>[^/.]+)/render",
        renderer_classes=[StaticHTMLRenderer],
    )
    def render_sent_to_as_html(self, request: Request, sent_to_id: str, *args: tuple, **kwargs: dict) -> Response:
        return Response(data=get_object_or_404(self.get_object().sent_to_list.all(), pk=sent_to_id).render_as_html())


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_EMAIL]) for m in HISTORY_METHODS})
class EmailNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    serializer_class = EmailNotificationHistoryAdminSerializer
    queryset = (
        EmailNotificationHistory.objects.filter_active()
        .select_related_with_user("template")
        .prefetch_related("sent_to_list")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_KAKAO_ALIMTALK]) for m in HISTORY_METHODS})
class NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    serializer_class = NHNCloudKakaoAlimTalkNotificationHistoryAdminSerializer
    queryset = (
        NHNCloudKakaoAlimTalkNotificationHistory.objects.filter_active()
        .select_related_with_user("template")
        .prefetch_related("sent_to_list")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_NOTI_SMS]) for m in HISTORY_METHODS})
class NHNCloudSMSNotificationHistoryAdminViewSet(_NotiHistoryAdminViewSetBase):
    serializer_class = NHNCloudSMSNotificationHistoryAdminSerializer
    queryset = (
        NHNCloudSMSNotificationHistory.objects.filter_active()
        .select_related_with_user("template")
        .prefetch_related("sent_to_list")
    )
