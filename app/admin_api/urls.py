from admin_api.views.cms import DomainGroupAdminViewSet, PageAdminViewSet, SitemapAdminViewSet
from admin_api.views.dashboard import DashboardChartAdminViewSet
from admin_api.views.document import DocumentTemplateAdminViewSet, IssuedDocumentAdminViewSet
from admin_api.views.event.event import EventAdminViewSet
from admin_api.views.event.presentation import (
    PresentationAdminViewSet,
    PresentationCategoryAdminViewSet,
    PresentationSpeakerAdminViewSet,
    PresentationTypeAdminViewSet,
    RoomAdminViewSet,
    RoomScheduleAdminViewSet,
)
from admin_api.views.event.sponsor import SponsorAdminViewSet, SponsorTagAdminViewSet, SponsorTierAdminViewSet
from admin_api.views.external_api.google_oauth2 import GoogleOAuth2AdminViewSet
from admin_api.views.file import PublicFileAdminViewSet
from admin_api.views.mcp_token import McpTokenAdminViewSet
from admin_api.views.modification_audit import ModificationAuditAdminViewSet
from admin_api.views.notification import (
    EmailNotificationHistoryAdminViewSet,
    EmailNotificationTemplateAdminViewSet,
    NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet,
    NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet,
    NHNCloudSMSNotificationHistoryAdminViewSet,
    NHNCloudSMSNotificationTemplateAdminViewSet,
)
from admin_api.views.shop.order_notifications import OrderNotificationAdminViewSet
from admin_api.views.shop.orders import OrderAdminViewSet
from admin_api.views.shop.products import (
    CategoryAdminViewSet,
    CategoryGroupAdminViewSet,
    OptionGroupAdminViewSet,
    ProductAdminViewSet,
    TagAdminViewSet,
)
from admin_api.views.shop.refund_authorizer import RefundAuthorizerAdminViewSet
from admin_api.views.socialaccount import (
    EmailAddressAdminViewSet,
    SocialAccountAdminViewSet,
    SocialAppAdminViewSet,
)
from admin_api.views.user import OrganizationAdminViewSet, UserAdminViewSet
from django.urls import include, path
from rest_framework import routers

# 라우트 컨벤션: <app_label 첫 segment>/<model_name>. (프론트 ChoicePicker 가 selectables 라우트를 모델 메타로 유도)
# 모델 없는 뷰셋(order-notifications, refund-authorizer, charts)은 유도 대상이 아니므로 기존 명시 라우트 유지.

admin_user_router = routers.SimpleRouter()
admin_user_router.register("userext", UserAdminViewSet, basename="admin-user")
admin_user_router.register("organization", OrganizationAdminViewSet, basename="admin-organization")
admin_user_router.register("mcptoken", McpTokenAdminViewSet, basename="admin-mcp-token")

admin_cms_router = routers.SimpleRouter()
admin_cms_router.register("domaingroup", DomainGroupAdminViewSet, basename="admin-domain-group")
admin_cms_router.register("sitemap", SitemapAdminViewSet, basename="admin-sitemap")
admin_cms_router.register("page", PageAdminViewSet, basename="admin-page")

admin_file_router = routers.SimpleRouter()
admin_file_router.register("publicfile", PublicFileAdminViewSet, basename="admin-public-file")

admin_event_router = routers.SimpleRouter()
admin_event_router.register("event", EventAdminViewSet)
admin_event_router.register("sponsortier", SponsorTierAdminViewSet)
admin_event_router.register("sponsortag", SponsorTagAdminViewSet)
admin_event_router.register("sponsor", SponsorAdminViewSet)
admin_event_router.register("presentationtype", PresentationTypeAdminViewSet)
admin_event_router.register("presentationcategory", PresentationCategoryAdminViewSet)
admin_event_router.register("presentation", PresentationAdminViewSet)
admin_event_router.register("presentationspeaker", PresentationSpeakerAdminViewSet)
admin_event_router.register("room", RoomAdminViewSet)
admin_event_router.register("roomschedule", RoomScheduleAdminViewSet)

admin_participant_portal_router = routers.SimpleRouter()
admin_participant_portal_router.register(
    "modificationaudit", ModificationAuditAdminViewSet, basename="admin-modification-audit"
)

admin_notification_router = routers.SimpleRouter()
admin_notification_router.register(
    "emailnotificationtemplate", EmailNotificationTemplateAdminViewSet, basename="admin-notification-email-template"
)
admin_notification_router.register(
    "emailnotificationhistory", EmailNotificationHistoryAdminViewSet, basename="admin-notification-email-history"
)
admin_notification_router.register(
    "nhncloudkakaoalimtalknotificationtemplate",
    NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet,
    basename="admin-notification-kakao-template",
)
admin_notification_router.register(
    "nhncloudkakaoalimtalknotificationhistory",
    NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet,
    basename="admin-notification-kakao-history",
)
admin_notification_router.register(
    "nhncloudsmsnotificationtemplate",
    NHNCloudSMSNotificationTemplateAdminViewSet,
    basename="admin-notification-sms-template",
)
admin_notification_router.register(
    "nhncloudsmsnotificationhistory",
    NHNCloudSMSNotificationHistoryAdminViewSet,
    basename="admin-notification-sms-history",
)

admin_external_api_router = routers.SimpleRouter()
admin_external_api_router.register("googleoauth2", GoogleOAuth2AdminViewSet, basename="admin-google-oauth2")

admin_shop_router = routers.SimpleRouter()
admin_shop_router.register("order", OrderAdminViewSet, basename="admin-shop-order")
admin_shop_router.register(
    "order-notifications", OrderNotificationAdminViewSet, basename="admin-shop-order-notification"
)
admin_shop_router.register("product", ProductAdminViewSet, basename="admin-shop-product")
admin_shop_router.register("category", CategoryAdminViewSet, basename="admin-shop-category")
admin_shop_router.register("tag", TagAdminViewSet, basename="admin-shop-tag")
admin_shop_router.register("categorygroup", CategoryGroupAdminViewSet, basename="admin-shop-category-group")
admin_shop_router.register("optiongroup", OptionGroupAdminViewSet, basename="admin-shop-option-group")
admin_shop_router.register("refund-authorizer", RefundAuthorizerAdminViewSet, basename="admin-shop-refund-authorizer")

admin_document_router = routers.SimpleRouter()
admin_document_router.register("documenttemplate", DocumentTemplateAdminViewSet, basename="admin-document-template")
admin_document_router.register("issueddocument", IssuedDocumentAdminViewSet, basename="admin-document-issued")

admin_dashboard_router = routers.SimpleRouter()
admin_dashboard_router.register("charts", DashboardChartAdminViewSet, basename="admin-dashboard-chart")

admin_allauth_router = routers.SimpleRouter()
admin_allauth_router.register("socialapp", SocialAppAdminViewSet, basename="admin-social-app")
admin_allauth_router.register("socialaccount", SocialAccountAdminViewSet, basename="admin-social-account")
admin_allauth_router.register("emailaddress", EmailAddressAdminViewSet, basename="admin-email-address")

urlpatterns = [
    path("cms/", include(admin_cms_router.urls)),
    path("file/", include(admin_file_router.urls)),
    path("user/", include(admin_user_router.urls)),
    path("event/", include(admin_event_router.urls)),
    path("participant_portal_api/", include(admin_participant_portal_router.urls)),
    path("notification/", include(admin_notification_router.urls)),
    path("external_api/", include(admin_external_api_router.urls)),
    path("shop/", include(admin_shop_router.urls)),
    path("document/", include(admin_document_router.urls)),
    path("dashboard/", include(admin_dashboard_router.urls)),
    path("allauth/", include(admin_allauth_router.urls)),
]
