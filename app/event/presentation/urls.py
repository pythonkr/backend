from django.urls import include, path
from event.presentation import views
from rest_framework import routers

cms_router = routers.SimpleRouter()
cms_router.register("category", views.PresentationCategoryViewSet, basename="presentation-category")
cms_router.register("", views.PresentationViewSet, basename="presentation")

bookmark_router = routers.SimpleRouter()
bookmark_router.register("bookmarks", views.PresentationBookmarkViewSet, basename="presentation-bookmark")

urlpatterns = [
    path("", include(bookmark_router.urls)),
    path("", include(cms_router.urls)),
]
