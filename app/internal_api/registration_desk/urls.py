from django.urls import include, path
from internal_api.registration_desk import views
from rest_framework import routers

router = routers.SimpleRouter()
router.register("orders", views.RegistrationDeskOrderViewSet, basename="orders")
router.register("order-products", views.RegistrationDeskOrderProductViewSet, basename="order-products")
router.register("", views.RegistrationDeskViewSet, basename="desk")

app_name = "registration_desk"

urlpatterns = [path("", include(router.urls))]
