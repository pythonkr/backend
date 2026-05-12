from django.urls import include, path
from rest_framework import routers
from shop.payment_history import views

router = routers.SimpleRouter()
router.register("", views.PaymentHistoryViewSet, basename="payment_histories")

urlpatterns = [path("", include(router.urls))]
