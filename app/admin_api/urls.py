from admin_api.views.cms import PageAdminViewSet, SitemapAdminViewSet
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
from admin_api.views.file import PublicFileAdminViewSet
from admin_api.views.modification_audit import ModificationAuditAdminViewSet
from admin_api.views.notification import (
    EmailNotificationHistoryAdminViewSet,
    EmailNotificationTemplateAdminViewSet,
    NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet,
    NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet,
    NHNCloudSMSNotificationHistoryAdminViewSet,
    NHNCloudSMSNotificationTemplateAdminViewSet,
)
from admin_api.views.user import OrganizationAdminViewSet, UserAdminViewSet
from django.urls import include, path
from rest_framework import routers

admin_user_router = routers.SimpleRouter()
admin_user_router.register("userext", UserAdminViewSet, basename="admin-user")
admin_user_router.register("organization", OrganizationAdminViewSet, basename="admin-organization")

admin_cms_router = routers.SimpleRouter()
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

admin_modificationaudit_router = routers.SimpleRouter()
admin_modificationaudit_router.register(
    "modification-audit", ModificationAuditAdminViewSet, basename="admin-modification-audit"
)

admin_notification_email_router = routers.SimpleRouter()
admin_notification_email_router.register(
    "template", EmailNotificationTemplateAdminViewSet, basename="admin-notification-email-template"
)
admin_notification_email_router.register(
    "history", EmailNotificationHistoryAdminViewSet, basename="admin-notification-email-history"
)

admin_notification_kakao_router = routers.SimpleRouter()
admin_notification_kakao_router.register(
    "template",
    NHNCloudKakaoAlimTalkNotificationTemplateAdminViewSet,
    basename="admin-notification-kakao-template",
)
admin_notification_kakao_router.register(
    "history",
    NHNCloudKakaoAlimTalkNotificationHistoryAdminViewSet,
    basename="admin-notification-kakao-history",
)

admin_notification_sms_router = routers.SimpleRouter()
admin_notification_sms_router.register(
    "template", NHNCloudSMSNotificationTemplateAdminViewSet, basename="admin-notification-sms-template"
)
admin_notification_sms_router.register(
    "history", NHNCloudSMSNotificationHistoryAdminViewSet, basename="admin-notification-sms-history"
)

urlpatterns = [
    path("cms/", include(admin_cms_router.urls)),
    path("file/", include(admin_file_router.urls)),
    path("user/", include(admin_user_router.urls)),
    path("event/", include(admin_event_router.urls)),
    path("modification-audit/", include(admin_modificationaudit_router.urls)),
    path("notification/email/", include(admin_notification_email_router.urls)),
    path("notification/kakao-alimtalk/", include(admin_notification_kakao_router.urls)),
    path("notification/sms/", include(admin_notification_sms_router.urls)),
]
