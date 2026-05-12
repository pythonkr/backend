from core.const.regex import UUID_V4_PATTERN
from django.urls import include, path
from rest_framework import routers
from shop.order import views

router = routers.SimpleRouter()
router.register("cart", views.CartViewSet, basename="cart")
router.register("cart/products", views.CartProductViewSet, basename="cart-products")
router.register("", views.OrderViewSet, basename="orders")
router.register(f"(?P<order_id>{UUID_V4_PATTERN})/products", views.OrderProductViewSet, basename="order-products")
router.register("scancode", views.ScanCodeViewSet, basename="scancode")

urlpatterns = [path("", include(router.urls))]
