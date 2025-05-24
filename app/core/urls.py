"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import core.health_check
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path, resolvers
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# type: ignore[assignment]
v1_apis: list[resolvers.URLPattern | resolvers.URLResolver] = [path("cms/", include("cms.urls"))]

urlpatterns = [
    # Health Check
    path("readyz/", core.health_check.readyz),
    path("livez/", core.health_check.livez),
    # Admin
    path("admin/", admin.site.urls),
    # V1 API
    re_path("^v1/", include((v1_apis, "v1"), namespace="v1")),
] + [
    # Static files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
]

if settings.DEBUG:
    urlpatterns += [
        # API Docs
        path("api/schema/v1/", SpectacularAPIView.as_view(api_version="v1"), name="v1-schema"),
        path("api/schema/v1/swagger/", SpectacularSwaggerView.as_view(url_name="v1-schema"), name="swagger-v1-ui"),
    ]
