from admin_api.views.cms import PageAdminViewSet, SitemapAdminViewSet
from admin_api.views.file import PublicFileAdminViewSet
from admin_api.views.user import UserAdminViewSet
from django.urls import include, path
from rest_framework import routers

admin_user_router = routers.SimpleRouter()
admin_user_router.register("userext", UserAdminViewSet, basename="admin-user")

admin_cms_router = routers.SimpleRouter()
admin_cms_router.register("sitemap", SitemapAdminViewSet, basename="admin-sitemap")
admin_cms_router.register("page", PageAdminViewSet, basename="admin-page")

admin_file_router = routers.SimpleRouter()
admin_file_router.register("publicfile", PublicFileAdminViewSet, basename="admin-public-file")

urlpatterns = [
    path("cms/", include(admin_cms_router.urls)),
    path("file/", include(admin_file_router.urls)),
    path("user/", include(admin_user_router.urls)),
]
