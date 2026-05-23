import pytest
from shop.order.models import CustomerInfo, SingleProductCart
from shop.serializers.cart_validation import OrderableCheckSerializerMode, SingleProductCartOrderableCheckSerializer
from shop.test.helpers import make_serializer_context


@pytest.mark.django_db
def test_single_product_cart_create_persists_opr_cart_and_customer_info(customer_user, product):
    serializer = SingleProductCartOrderableCheckSerializer(
        data={
            "product": str(product.id),
            "options": [],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "buyer@example.com",
                "organization": "",
            },
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid()

    opr = serializer.save()

    assert opr.product == product
    cart = SingleProductCart.objects.get(order_product_relation=opr)
    assert cart.user == customer_user
    assert CustomerInfo.objects.filter(single_product_cart=cart, name="홍길동").exists()


@pytest.mark.django_db
def test_single_product_cart_forces_checkout_single_product_mode(customer_user, product):
    # context 에 mode 를 임의 override 해도 validation_mode property 가 강제로 CHECKOUT_SINGLE_PRODUCT 반환.
    serializer = SingleProductCartOrderableCheckSerializer(
        data={
            "product": str(product.id),
            "options": [],
            "customer_info": {
                "name": "홍길동",
                "phone": "010-1234-5678",
                "email": "buyer@example.com",
                "organization": "",
            },
        },
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT
