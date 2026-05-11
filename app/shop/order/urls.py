from django.urls import include, path
from rest_framework import routers
from shop.order import views

router = routers.SimpleRouter()
router.register("cart", views.CartViewSet, basename="cart")
router.register("cart/products", views.CartProductViewSet, basename="cart-products")
router.register("order-products/scancode", views.OrderProductScanCodeViewSet, basename="order-products-scancode")
router.register("", views.OrderViewSet, basename="orders")
router.register("(?P<order_id>[0-9a-f-]*)/products", views.OrderProductViewSet, basename="order-products")

urlpatterns = [path("", include(router.urls))]
