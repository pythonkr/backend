from django.urls import include, path
from external_api.google_oauth2 import urls as google_oauth2_urls

urlpatterns = [
    path("google/", include(google_oauth2_urls.urlpatterns)),
]
