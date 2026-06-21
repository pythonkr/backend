from django.urls import include, path
from event import views
from rest_framework import routers

router = routers.SimpleRouter()
router.register("", views.EventViewSet, basename="event")

urlpatterns = [path("", include(router.urls))]
