from admin_api.views.cms import PageAdminViewSet, SitemapAdminViewSet
from admin_api.views.event.event import EventAdminViewSet
from admin_api.views.event.presentation import (
    PresentationAdminViewSet,
    PresentationCategoryAdminViewSet,
    PresentationSpeakerAdminViewSet,
    PresentationTypeAdminViewSet,
)
from admin_api.views.event.sponsor import SponsorAdminViewSet, SponsorTagAdminViewSet, SponsorTierAdminViewSet
from admin_api.views.file import PublicFileAdminViewSet
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

urlpatterns = [
    path("cms/", include(admin_cms_router.urls)),
    path("file/", include(admin_file_router.urls)),
    path("user/", include(admin_user_router.urls)),
    path("event/", include(admin_event_router.urls)),
]
