from django.urls import include, path

urlpatterns = [path("registration-desk/", include("internal_api.registration_desk.urls"))]
