from django.urls import include, path
from event.sponsor import views
from rest_framework import routers

cms_router = routers.SimpleRouter()
cms_router.register("sponsors", views.SponsorViewSet, basename="sponsor")

urlpatterns = [path("", include(cms_router.urls))]
