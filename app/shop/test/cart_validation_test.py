from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import (
    CartNotOrderableErrorMessages,
    OptionGroupNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
    TagNotOrderableErrorMessages,
)
from core.util.testutil import errors_payload
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart
from shop.product.models import OptionGroup, Product
from shop.serializers.cart_validation import (
    CartOrderableCheckSerializer,
    OptionOrderableCheckSerializer,
    OrderableCheckSerializerMode,
    ProductOrderableCheckSerializer,
    SingleProductCartOrderableCheckSerializer,
    TagOrderableCheckSerializer,
)
from shop.test.helpers import make_serializer_context


@pytest.mark.django_db
def test_cart_rejects_other_users_cart_via_queryset_boundary(pending_order, other_user):
    # 보안 boundary — `__init__` 의 queryset 재설정이 타인의 cart PK 를 차단.
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(pending_order.id)}, context=make_serializer_context(other_user)
    )
    assert serializer.is_valid() is False
    # PrimaryKeyRelatedField 의 "does not exist" 에러 — 본인 cart 만 쿼리되므로 타인 cart PK 는 매칭 0건.
    assert "cart" in serializer.errors


@pytest.mark.django_db
def test_cart_rejects_already_paid_cart_via_queryset_boundary(completed_order, customer_user):
    # filter_has_no_payment_histories 가 queryset 에서 결제된 cart 를 제외 — PK 매칭 0건.
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(completed_order.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert "cart" in serializer.errors


@pytest.mark.django_db
def test_cart_rejects_when_contains_paid_product(pending_order, customer_user):
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
def test_cart_passes_for_valid_pending_cart(pending_order, customer_user):
    serializer = CartOrderableCheckSerializer(
        data={"cart": str(pending_order.id)}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid()


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))  # _FAR_PAST(2020) 이전 → orderable window 밖.
@pytest.mark.django_db
def test_product_rejects_when_outside_orderable_window(product, customer_user):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {"detail": ProductNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(product.name), "code": "invalid"}
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_soldout(customer_user, product, other_user):
    # stock=1, 다른 user 가 1건 paid → leftover=0 → SOLDOUT.
    product.stock = 1
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="other"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [{"detail": ProductNotOrderableErrorMessages.SOLDOUT.format(product.name), "code": "invalid"}],
    }


@pytest.mark.django_db
def test_product_rejects_when_cart_overflow_in_add_mode(customer_user, product):
    # ADD_SINGLE_PRODUCT_TO_CART (default): cart 누적 + 1 > leftover_stock 이면 거절.
    product.stock = 1
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=product,
        price=product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {"detail": ProductNotOrderableErrorMessages.TOO_MUCH_CART_PRODUCT.format(product.name), "code": "invalid"}
        ],
    }


@pytest.mark.django_db
def test_product_ignores_cart_count_in_checkout_single_product_mode(customer_user, product):
    # CHECKOUT_SINGLE_PRODUCT 는 cart 누적을 무시 — overflow 와 같은 setup 이라도 통과.
    product.stock = 1
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=product,
        price=product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_max_quantity_per_user_exceeded(customer_user, product):
    # 이미 1개 구매한 상태에서 추가 1개 시도 → 인당 한도 초과.
    product.max_quantity_per_user = 1
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="purchased"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {
                "detail": ProductNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(product.name),
                "code": "invalid",
            }
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_option_does_not_belong_to_product(customer_user, product, option_group, option):
    # 다른 product 의 옵션을 첨부 → OPTION_NOT_MATCH_PRODUCT.
    other_product = Product.objects.create(
        category=product.category,
        name="other",
        price=1000,
        stock=10,
        visible_starts_at=product.visible_starts_at,
        visible_ends_at=product.visible_ends_at,
        orderable_starts_at=product.orderable_starts_at,
        orderable_ends_at=product.orderable_ends_at,
    )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(other_product.id),
            "options": [
                {
                    "product_option_group": str(option_group.id),
                    "product_option": str(option.id),
                    "custom_response": None,
                },
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.OPTION_NOT_MATCH_PRODUCT.format(other_product.name),
                "code": "invalid",
            }
        ],
    }


@pytest.mark.parametrize(
    ("product_overrides", "donation_price", "expected_error_factory"),
    [
        pytest.param(
            {"donation_allowed": False},
            1000,
            lambda product: ProductNotOrderableErrorMessages.DONATION_NOT_ALLOWED.format(product.name),
            id="donation_not_allowed_but_price_given",
        ),
        pytest.param(
            {"donation_allowed": True, "donation_min_price": 1000, "donation_max_price": 5000},
            500,
            lambda product: ProductNotOrderableErrorMessages.DONATION_PRICE_OUT_OF_RANGE.format(
                product.name, 1000, 5000
            ),
            id="donation_price_below_min",
        ),
        pytest.param(
            {"donation_allowed": True, "donation_max_price": 1_000_000},
            1_000_000 - 10000,  # product.price=10000 → total=1_000_000 (>=1M)
            lambda _product: ProductNotOrderableErrorMessages.PRICE_TOO_HIGH,
            id="total_price_too_high",
        ),
    ],
)
@pytest.mark.django_db
def test_product_rejects_donation_invariants(
    customer_user, product, product_overrides, donation_price, expected_error_factory
):
    for attr, value in product_overrides.items():
        setattr(product, attr, value)
    product.save()

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": [], "donation_price": donation_price},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": expected_error_factory(product), "code": "invalid"}],
    }


@pytest.mark.django_db
def test_product_passes_happy_path(customer_user, product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_option_group_rejects_when_stock_insufficient_for_min_quantity(customer_user, option_group, option):
    # group.min_quantity_per_product=5, option.stock=1 → sum=1 < 5 → group SOLDOUT.
    # option 자체는 leftover=1 > 0 이라 option-level SOLDOUT 미발생 — group-level 단독 검증.
    option_group.min_quantity_per_product = 5
    option_group.save()
    option.stock = 1
    option.save()

    serializer = OptionOrderableCheckSerializer(
        data={
            "product_option_group": str(option_group.id),
            "product_option": str(option.id),
            "custom_response": None,
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product_option_group": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.SOLDOUT.format(
                    option_group.product.name, option_group.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_option_rejects_when_option_is_none_for_non_custom_response_group(customer_user, option_group):
    # option=None + group.is_custom_response=False → OPTION_NOT_SELECTED.
    serializer = OptionOrderableCheckSerializer(
        data={"product_option_group": str(option_group.id), "product_option": None, "custom_response": None},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product_option": [{"detail": OptionGroupNotOrderableErrorMessages.OPTION_NOT_SELECTED, "code": "invalid"}],
    }


@pytest.mark.django_db
def test_option_rejects_when_user_not_signed_in(option_group):
    serializer = OptionOrderableCheckSerializer(
        data={"product_option_group": str(option_group.id), "product_option": None, "custom_response": None},
        context=make_serializer_context(AnonymousUser()),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product_option": [{"detail": SignInErrorMessages.USER_NOT_SIGNED_IN, "code": "invalid"}],
    }


@pytest.mark.django_db
def test_custom_response_rejects_when_pattern_mismatch(customer_user, product):
    # is_custom_response=True 그룹에 pattern 위배 응답.
    group = OptionGroup.objects.create(
        product=product,
        name="custom",
        is_custom_response=True,
        custom_response_pattern=r"^\d{6}$",
    )
    serializer = OptionOrderableCheckSerializer(
        data={"product_option_group": str(group.id), "product_option": None, "custom_response": "abc"},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "custom_response": [
            {"detail": OptionGroupNotOrderableErrorMessages.CUSTOM_RESPONSE_PATTERN_MISMATCH, "code": "invalid"},
        ],
    }


@pytest.mark.django_db
def test_option_passes_happy_path(customer_user, option_group, option):
    serializer = OptionOrderableCheckSerializer(
        data={
            "product_option_group": str(option_group.id),
            "product_option": str(option.id),
            "custom_response": None,
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid()


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
