from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import (
    OptionGroupNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
)
from core.util.testutil import errors_payload, pk_does_not_exist_error
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.product.models import OptionGroup, Product
from shop.serializers.cart_validation import OrderableCheckSerializerMode, ProductOrderableCheckSerializer
from shop.test.helpers import make_serializer_context


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
        pytest.param(
            {"price": 0},
            0,
            lambda _product: ProductNotOrderableErrorMessages.PRICE_TOO_LOW,
            id="total_price_is_zero",
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
def test_product_create_in_add_mode_appends_to_existing_unpaid_cart(customer_user, product):
    # 기존 unpaid Order(cart) 있음 → 동일 cart 에 OPR append.
    existing_cart = Order.objects.create(user=customer_user, name="cart")
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.order_id == existing_cart.id
    assert opr.product == product


@pytest.mark.django_db
def test_product_create_in_add_mode_creates_cart_when_none_exists(customer_user, product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.order is not None
    assert opr.order.user == customer_user


@pytest.mark.django_db
def test_product_create_in_checkout_single_product_mode_creates_cart_and_options(
    customer_user, product, option_group, option
):
    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(product.id),
            "options": [
                {
                    "product_option_group": str(option_group.id),
                    "product_option": str(option.id),
                    "custom_response": None,
                },
            ],
        },
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT),
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.order is None
    assert SingleProductCart.objects.filter(order_product_relation=opr, user=customer_user).exists()
    assert OrderProductOptionRelation.objects.filter(order_product_relation=opr, product_option=option).exists()


@pytest.mark.django_db
def test_product_create_in_checkout_cart_mode_raises_invalid_logic(customer_user, product):
    # validate() 통과 후 create() 가 CHECKOUT_CART 로 호출되는 것은 logic error — 마지막 else 분기로 거부.
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_CART),
    )
    assert serializer.is_valid()
    with pytest.raises(ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_product_orderable_rejects_soft_deleted_product(customer_user, product):
    # queryset=Product.objects.filter(deleted_at__isnull=True) — soft-delete 된 product PK 는 매칭 0건.
    product.delete()

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"product": [pk_does_not_exist_error(product.id)]}


@pytest.mark.django_db
def test_product_orderable_rejects_negative_donation_price(customer_user, product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": [], "donation_price": -1},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "donation_price": [{"detail": "이 값이 0보다 크거나 같은지 확인하세요.", "code": "min_value"}],
    }


@pytest.mark.django_db
def test_product_orderable_rejects_null_options(customer_user, product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": None}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "options": [{"detail": "이 필드는 null일 수 없습니다.", "code": "null"}],
    }


@pytest.mark.django_db
def test_product_rejects_when_user_not_signed_in(product):
    # validate_product 의 self.user property — 비인증 시 USER_NOT_SIGNED_IN.
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []}, context=make_serializer_context(AnonymousUser())
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [{"detail": SignInErrorMessages.USER_NOT_SIGNED_IN, "code": "invalid"}],
    }


@pytest.mark.parametrize(
    ("mode", "purchased_count", "cart_count"),
    [
        # ADD: cart + purchased + 1, max=1 위배.
        (OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART, 0, 1),
        # CHECKOUT_SINGLE_PRODUCT: purchased + 1, max=1 위배.
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 1, 0),
        # CHECKOUT_CART: cart + purchased, max=1 위배.
        (OrderableCheckSerializerMode.CHECKOUT_CART, 1, 1),
    ],
)
@pytest.mark.django_db
def test_product_rejects_when_max_quantity_exceeded_per_mode(customer_user, product, mode, purchased_count, cart_count):
    product.max_quantity_per_user = 1
    product.save()
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

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False


@pytest.mark.django_db
def test_product_in_checkout_cart_mode_passes_overflow_setup(customer_user, product):
    # CHECKOUT_CART mode 는 cart 누적을 그대로 사용 — overflow 시점에서 1 > 1 위배되지 않음 (= 비교 아닌 >).
    product.stock = 1
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=product,
        price=product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_CART),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_option_group_min_quantity_not_met(customer_user, product):
    # min_quantity_per_product=2, options=[] → 선택 수량 0 < 2 → NOT_ENOUGH_OPTION.
    group = OptionGroup.objects.create(product=product, name="필수옵션", min_quantity_per_product=2)
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(product.id), "options": []},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.NOT_ENOUGH_OPTION.format(product.name, group.name),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_option_group_max_quantity_exceeded(customer_user, product):
    # max_quantity_per_product=1, options=[2개] → 1 초과 → TOO_MUCH_OPTION.
    group = OptionGroup.objects.create(product=product, name="옵션", max_quantity_per_product=1)
    opt_a = group.options.create(name="A")
    opt_b = group.options.create(name="B")

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt_a.id), "custom_response": None},
                {"product_option_group": str(group.id), "product_option": str(opt_b.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.TOO_MUCH_OPTION.format(product.name, group.name),
                "code": "invalid",
            },
        ],
    }
