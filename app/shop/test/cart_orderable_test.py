import pytest
from core.const.shop_error_messages import CartNotOrderableErrorMessages
from core.util.testutil import errors_payload
from rest_framework.exceptions import ValidationError
from shop.order.models import Order, OrderProductRelation
from shop.serializers.cart_validation import CartOrderableCheckSerializer
from shop.test.helpers import make_serializer_context


@pytest.mark.django_db
def test_cart_rejects_other_users_cart_via_queryset_boundary(other_user, order_factory):
    pending_order = order_factory()
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(pending_order.id)}, context=make_serializer_context(other_user)
    )
    assert serializer.is_valid() is False
    # PrimaryKeyRelatedField 의 "does not exist" 에러 — 본인 cart 만 쿼리되므로 타인 cart PK 는 매칭 0건.
    assert "cart" in serializer.errors


@pytest.mark.django_db
def test_cart_rejects_already_paid_cart_via_queryset_boundary(customer_user, order_factory):
    completed_order = order_factory(status="completed")
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(completed_order.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert "cart" in serializer.errors


@pytest.mark.django_db
def test_cart_rejects_when_contains_paid_product(customer_user, order_factory):
    pending_order = order_factory()
    pending_order.products.update(status=OrderProductRelation.OrderProductStatus.paid)
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(pending_order.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": CartNotOrderableErrorMessages.CONTAINS_PAID_PRODUCT, "code": "invalid"}],
    }


@pytest.mark.django_db
def test_cart_rejects_when_price_is_zero_or_negative(customer_user, product):
    # OPR 없이 빈 cart — first_paid_price=0 → CART_PRICE_TOO_LOW.
    empty_cart = Order.objects.create(user=customer_user, name="empty")
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(empty_cart.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": CartNotOrderableErrorMessages.CART_PRICE_TOO_LOW, "code": "invalid"}],
    }


@pytest.mark.django_db
def test_cart_rejects_when_price_too_high(customer_user, product):
    # OPR 가격 1_000_000 이상 → CART_PRICE_TOO_HIGH.
    cart = Order.objects.create(user=customer_user, name="expensive")
    OrderProductRelation.objects.create(order=cart, product=product, price=1_000_000)
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(cart.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": CartNotOrderableErrorMessages.CART_PRICE_TOO_HIGH, "code": "invalid"}],
    }


@pytest.mark.django_db
def test_cart_passes_for_valid_pending_cart(customer_user, order_factory):
    pending_order = order_factory()
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(pending_order.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_cart_validate_defensively_rejects_paid_cart(customer_user, order_factory):
    completed_order = order_factory(status="completed")
    serializer = CartOrderableCheckSerializer(context=make_serializer_context(customer_user))
    with pytest.raises(ValidationError) as exc_info:
        serializer.validate({"cart": completed_order})
    assert exc_info.value.detail[0] == CartNotOrderableErrorMessages.ALREADY_ORDERED
