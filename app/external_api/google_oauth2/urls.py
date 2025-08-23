from django.urls import include, path
from external_api.google_oauth2.views import GoogleOAuth2ViewSet
from rest_framework import routers

google_router = routers.SimpleRouter()
google_router.register("oauth2", GoogleOAuth2ViewSet, basename="google-oauth2")

urlpatterns = [
    path("", include(google_router.urls)),
]
