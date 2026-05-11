from django.urls import include, path
from internal_api import views
from rest_framework import routers

router = routers.SimpleRouter()
router.register("desk-support", views.DeskSupportViewSet, basename="desk-support")

urlpatterns = [path("", include(router.urls))]
