from django.urls import include, path
from rest_framework import routers
from shop.product import views

router = routers.SimpleRouter()
router.register("", views.ProductViewSet, basename="products")

urlpatterns = [path("", include(router.urls))]
