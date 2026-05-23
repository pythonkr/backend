import pytest
from core.const.shop_error_messages import SignInErrorMessages, TagNotOrderableErrorMessages
from core.util.testutil import errors_payload
from django.contrib.auth.models import AnonymousUser
from shop.order.models import Order, OrderProductRelation
from shop.serializers.cart_validation import OrderableCheckSerializerMode, TagOrderableCheckSerializer
from shop.test.helpers import make_serializer_context


@pytest.mark.django_db
def test_tag_rejects_when_soldout(customer_user, tag, other_user):
    # tag.stock=1, 다른 user 가 해당 tag 의 product 를 1건 paid → leftover=0.
    tag.stock = 1
    tag.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="other"),
        product=tag.products.first().product,
        price=10000,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = TagOrderableCheckSerializer(
        instance=tag, data={}, context=make_serializer_context(customer_user), partial=True
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": TagNotOrderableErrorMessages.SOLDOUT.format(tag.name), "code": "invalid"}],
    }


@pytest.mark.django_db
def test_tag_rejects_when_user_max_quantity_exceeded(customer_user, tag, product):
    tag.max_quantity_per_user = 1
    tag.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="purchased"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = TagOrderableCheckSerializer(
        instance=tag, data={}, context=make_serializer_context(customer_user), partial=True
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": TagNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH_RELATED_PRODUCTS.format(tag.name),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_tag_passes_happy_path(customer_user, tag):
    serializer = TagOrderableCheckSerializer(
        instance=tag, data={}, context=make_serializer_context(customer_user), partial=True
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_tag_rejects_when_user_not_signed_in(tag):
    # tag.max_quantity_per_user > 0 일 때 self.user 접근 → AnonymousUser 거절.
    tag.max_quantity_per_user = 1
    tag.save()

    serializer = TagOrderableCheckSerializer(
        instance=tag, data={}, context=make_serializer_context(AnonymousUser()), partial=True
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": SignInErrorMessages.USER_NOT_SIGNED_IN, "code": "invalid"}],
    }


@pytest.mark.parametrize(
    ("mode", "purchased_count", "cart_count"),
    [
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 1, 0),
        (OrderableCheckSerializerMode.CHECKOUT_CART, 1, 1),
    ],
)
@pytest.mark.django_db
def test_tag_max_quantity_per_user_exceeded_per_mode(customer_user, tag, product, mode, purchased_count, cart_count):
    tag.max_quantity_per_user = 1
    tag.save()
    for _ in range(purchased_count):
        OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="paid"),
            product=product,
            price=product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )
    for _ in range(cart_count):
        OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=product,
            price=product.price,
        )

    serializer = TagOrderableCheckSerializer(
        instance=tag, data={}, context=make_serializer_context(customer_user, mode=mode), partial=True
    )
    assert serializer.is_valid() is False
