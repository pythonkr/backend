from django.urls import include, path

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("authn/social/", include("allauth.headless.urls")),
    path("", include("user.urls")),
]
