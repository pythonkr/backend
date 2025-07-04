from django.urls import include, path
from participant_portal_api.views.file import PublicFilePortalViewSet
from participant_portal_api.views.modification_audit import ModificationAuditPortalViewSet
from participant_portal_api.views.presentation import PresentationPortalViewSet
from participant_portal_api.views.user import UserPortalViewSet
from rest_framework import routers

participant_router = routers.SimpleRouter()
participant_router.register("user", UserPortalViewSet, basename="participant-user")
participant_router.register("public-file", PublicFilePortalViewSet, basename="participant-publicfile")
participant_router.register("presentation", PresentationPortalViewSet, basename="participant-presentation")
participant_router.register(
    "modification-audit", ModificationAuditPortalViewSet, basename="participant-modification-audit"
)

urlpatterns = [path("", include(participant_router.urls))]
