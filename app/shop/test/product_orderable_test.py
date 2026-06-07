from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import (
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
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


# 이 파일은 일반 상품(non_ticket_product) 기준 주문 검증 — 티켓의 ticket_info 인라인 필수/생성은 ticket_info_test 에서 별도 검증.
@pytest.fixture
def option_group(non_ticket_product) -> OptionGroup:
    """옵션 그룹을 비티켓 상품에 매단다 — conftest 의 티켓 기반 option_group 을 이 파일에서 override."""
    return OptionGroup.objects.create(product=non_ticket_product, name="사이즈")


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))  # _FAR_PAST(2020) 이전 → orderable window 밖.
@pytest.mark.django_db
def test_product_rejects_when_outside_orderable_window(non_ticket_product, customer_user):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {
                "detail": ProductNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(non_ticket_product.name),
                "code": "invalid",
            }
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_soldout(customer_user, non_ticket_product, other_user):
    # stock=1, 다른 user 가 1건 paid → leftover=0 → SOLDOUT.
    non_ticket_product.stock = 1
    non_ticket_product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="other"),
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {"detail": ProductNotOrderableErrorMessages.SOLDOUT.format(non_ticket_product.name), "code": "invalid"}
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_cart_overflow_in_add_mode(customer_user, non_ticket_product):
    # ADD_SINGLE_PRODUCT_TO_CART (default): cart 누적 + 1 > leftover_stock 이면 거절.
    non_ticket_product.stock = 1
    non_ticket_product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=non_ticket_product,
        price=non_ticket_product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {
                "detail": ProductNotOrderableErrorMessages.TOO_MUCH_CART_PRODUCT.format(non_ticket_product.name),
                "code": "invalid",
            }
        ],
    }


@pytest.mark.django_db
def test_product_ignores_cart_count_in_checkout_single_product_mode(customer_user, non_ticket_product):
    # CHECKOUT_SINGLE_PRODUCT 는 cart 누적을 무시 — overflow 와 같은 setup 이라도 통과.
    non_ticket_product.stock = 1
    non_ticket_product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=non_ticket_product,
        price=non_ticket_product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_max_quantity_per_user_exceeded(customer_user, non_ticket_product):
    # 이미 1개 구매한 상태에서 추가 1개 시도 → 인당 한도 초과.
    non_ticket_product.max_quantity_per_user = 1
    non_ticket_product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="purchased"),
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product": [
            {
                "detail": ProductNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(non_ticket_product.name),
                "code": "invalid",
            }
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_option_does_not_belong_to_product(
    customer_user, non_ticket_product, option_group, option
):
    # 다른 non_ticket_product 의 옵션을 첨부 → OPTION_NOT_MATCH_PRODUCT.
    other_product = Product.objects.create(
        category=non_ticket_product.category,
        name="other",
        price=1000,
        stock=10,
        visible_starts_at=non_ticket_product.visible_starts_at,
        visible_ends_at=non_ticket_product.visible_ends_at,
        orderable_starts_at=non_ticket_product.orderable_starts_at,
        orderable_ends_at=non_ticket_product.orderable_ends_at,
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
            lambda non_ticket_product: ProductNotOrderableErrorMessages.DONATION_NOT_ALLOWED.format(
                non_ticket_product.name
            ),
            id="donation_not_allowed_but_price_given",
        ),
        pytest.param(
            {"donation_allowed": True, "donation_min_price": 1000, "donation_max_price": 5000},
            500,
            lambda non_ticket_product: ProductNotOrderableErrorMessages.DONATION_PRICE_OUT_OF_RANGE.format(
                non_ticket_product.name, 1000, 5000
            ),
            id="donation_price_below_min",
        ),
        pytest.param(
            {"donation_allowed": True, "donation_max_price": 1_000_000},
            1_000_000 - 10000,  # non_ticket_product.price=10000 → total=1_000_000 (>=1M)
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
    customer_user, non_ticket_product, product_overrides, donation_price, expected_error_factory
):
    for attr, value in product_overrides.items():
        setattr(non_ticket_product, attr, value)
    non_ticket_product.save()

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": [], "donation_price": donation_price},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": expected_error_factory(non_ticket_product), "code": "invalid"}],
    }


@pytest.mark.django_db
def test_product_passes_happy_path(customer_user, non_ticket_product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_create_in_add_mode_appends_to_existing_unpaid_cart(customer_user, non_ticket_product):
    # 기존 unpaid Order(cart) 있음 → 동일 cart 에 OPR append.
    existing_cart = Order.objects.create(user=customer_user, name="cart")
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.order_id == existing_cart.id
    assert opr.product == non_ticket_product


@pytest.mark.django_db
def test_product_create_in_add_mode_creates_cart_when_none_exists(customer_user, non_ticket_product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.order is not None
    assert opr.order.user == customer_user


@pytest.mark.django_db
def test_product_create_in_checkout_single_product_mode_creates_cart_and_options(
    customer_user, non_ticket_product, option_group, option
):
    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
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
def test_product_create_in_checkout_cart_mode_raises_invalid_logic(customer_user, non_ticket_product):
    # validate() 통과 후 create() 가 CHECKOUT_CART 로 호출되는 것은 logic error — 마지막 else 분기로 거부.
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_CART),
    )
    assert serializer.is_valid()
    with pytest.raises(ValidationError):
        serializer.save()


@pytest.mark.django_db
def test_product_orderable_rejects_soft_deleted_product(customer_user, non_ticket_product):
    # queryset=Product.objects.filter(deleted_at__isnull=True) — soft-delete 된 non_ticket_product PK 는 매칭 0건.
    non_ticket_product.delete()

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"product": [pk_does_not_exist_error(non_ticket_product.id)]}


@pytest.mark.django_db
def test_product_orderable_rejects_negative_donation_price(customer_user, non_ticket_product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": [], "donation_price": -1},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "donation_price": [{"detail": "이 값이 0보다 크거나 같은지 확인하세요.", "code": "min_value"}],
    }


@pytest.mark.django_db
def test_product_orderable_rejects_null_options(customer_user, non_ticket_product):
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": None}, context=make_serializer_context(customer_user)
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "options": [{"detail": "이 필드는 null일 수 없습니다.", "code": "null"}],
    }


@pytest.mark.django_db
def test_product_rejects_when_user_not_signed_in(non_ticket_product):
    # validate_product 의 self.user property — 비인증 시 USER_NOT_SIGNED_IN.
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []}, context=make_serializer_context(AnonymousUser())
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
def test_product_rejects_when_max_quantity_exceeded_per_mode(
    customer_user, non_ticket_product, mode, purchased_count, cart_count
):
    non_ticket_product.max_quantity_per_user = 1
    non_ticket_product.save()
    for _ in range(purchased_count):
        OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="paid"),
            product=non_ticket_product,
            price=non_ticket_product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )
    for _ in range(cart_count):
        OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=non_ticket_product,
            price=non_ticket_product.price,
        )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False


@pytest.mark.django_db
def test_product_in_checkout_cart_mode_passes_overflow_setup(customer_user, non_ticket_product):
    # CHECKOUT_CART mode 는 cart 누적을 그대로 사용 — overflow 시점에서 1 > 1 위배되지 않음 (= 비교 아닌 >).
    non_ticket_product.stock = 1
    non_ticket_product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=non_ticket_product,
        price=non_ticket_product.price,
    )

    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.CHECKOUT_CART),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_option_group_min_quantity_not_met(customer_user, non_ticket_product):
    # min_quantity_per_product=2, options=[] → 선택 수량 0 < 2 → NOT_ENOUGH_OPTION.
    group = OptionGroup.objects.create(product=non_ticket_product, name="필수옵션", min_quantity_per_product=2)
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.NOT_ENOUGH_OPTION.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_rejects_when_option_group_visible_period_not_started(customer_user, non_ticket_product):
    # 그룹의 visible_starts_at(2031) 가 미래 → API 노출 안 되지만 직접 ID 주문 시도도 cart validation 에서 차단.
    group = OptionGroup.objects.create(
        product=non_ticket_product, name="후공개", visible_starts_at=datetime(2031, 1, 1, tzinfo=timezone.utc)
    )
    opt = group.options.create(name="A")

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_rejects_when_option_group_orderable_period_not_started(customer_user, non_ticket_product):
    # 그룹의 orderable_starts_at(2031) 가 현재(2030) 보다 미래 → 거절.
    group = OptionGroup.objects.create(
        product=non_ticket_product,
        name="얼리버드",
        orderable_starts_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
    )
    opt = group.options.create(name="A")

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.NOT_ORDERABLE_TIME.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_passes_when_option_group_in_unselected_period(customer_user, non_ticket_product):
    # 그룹은 기간 밖이지만 그 그룹에 옵션을 선택하지 않았으므로 검증 안 함.
    OptionGroup.objects.create(
        product=non_ticket_product,
        name="얼리버드",
        orderable_starts_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
    )
    serializer = ProductOrderableCheckSerializer(
        data={"product": str(non_ticket_product.id), "options": []},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_option_group_max_per_user_exceeded_in_single_request(customer_user, non_ticket_product):
    # group max=2 인데 group 내 옵션을 3개 (A,B,C) 한 번에 선택 → group 합산 3 > 2 → 거절.
    group = OptionGroup.objects.create(
        product=non_ticket_product, name="티셔츠", max_quantity_per_product=10, max_quantity_per_user=2
    )
    opts = [group.options.create(name=n) for n in ("A", "B", "C")]

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(o.id), "custom_response": None}
                for o in opts
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.parametrize(
    ("mode", "purchased_count", "cart_count", "in_request"),
    [
        # CHECKOUT_SINGLE: cart 무시, purchased + 이번 request → max=1 위배.
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 1, 0, 1),
        # CHECKOUT_CART: cart 누적 (자기 자신 포함, 이번 request 안 더함) → max=1 위배.
        (OrderableCheckSerializerMode.CHECKOUT_CART, 1, 1, 1),
    ],
)
@pytest.mark.django_db
def test_product_rejects_when_option_group_max_per_user_exceeded_per_mode(
    customer_user, non_ticket_product, mode, purchased_count, cart_count, in_request
):
    # OptionGroup max_per_user 검증의 CHECKOUT_* mode 분기 (#23).
    group = OptionGroup.objects.create(
        product=non_ticket_product, name="티셔츠", max_quantity_per_product=10, max_quantity_per_user=1
    )
    opt = group.options.create(name="A")
    for _ in range(purchased_count):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="paid"),
            product=non_ticket_product,
            price=non_ticket_product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=opt
        )
    for _ in range(cart_count):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=non_ticket_product,
            price=non_ticket_product.price,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=opt
        )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None}
                for _ in range(in_request)
            ],
        },
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionGroupNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.parametrize(
    ("mode", "cart_count", "in_request"),
    [
        # CHECKOUT_SINGLE: cart 무시, request N 만 leftover 비교 — N=2 > leftover=1.
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 0, 2),
        # CHECKOUT_CART: cart 누적만 (자기 포함) 비교 — cart 2 > leftover=1.
        (OrderableCheckSerializerMode.CHECKOUT_CART, 2, 1),
    ],
)
@pytest.mark.django_db
def test_product_rejects_when_aggregated_option_count_exceeds_leftover_per_mode(
    customer_user, non_ticket_product, mode, cart_count, in_request
):
    # 동일 option 합산 stock 검증의 CHECKOUT_* mode 분기 (#22).
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", stock=1)
    for _ in range(cart_count):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=non_ticket_product,
            price=non_ticket_product.price,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=opt
        )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None}
                for _ in range(in_request)
            ],
        },
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(
                    non_ticket_product.name, opt.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_option_group_max_per_user_already_taken_in_cart(customer_user, non_ticket_product):
    # group max=2, cart 에 이미 1개 + 이번 요청 2개 → 합산 3 > 2 → 거절.
    group = OptionGroup.objects.create(
        product=non_ticket_product, name="티셔츠", max_quantity_per_product=10, max_quantity_per_user=2
    )
    opt_a, opt_b = group.options.create(name="A"), group.options.create(name="B")

    cart_opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=non_ticket_product,
        price=non_ticket_product.price,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=cart_opr, product_option_group=group, product_option=opt_a
    )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
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
                "detail": OptionGroupNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_allows_option_group_within_max_per_user(customer_user, non_ticket_product):
    # group max=2, 이번 요청 2개 → 통과.
    group = OptionGroup.objects.create(
        product=non_ticket_product, name="티셔츠", max_quantity_per_product=10, max_quantity_per_user=2
    )
    opt_a, opt_b = group.options.create(name="A"), group.options.create(name="B")

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt_a.id), "custom_response": None},
                {"product_option_group": str(group.id), "product_option": str(opt_b.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_option_group_get_user_taken_stock_count_counts_per_group(customer_user, non_ticket_product, other_user):
    # 같은 group 의 옵션 2건 paid + 다른 group 옵션 1건 + 다른 user 옵션 1건 → 본 user, 본 group 만 2.
    group = OptionGroup.objects.create(product=non_ticket_product, name="티셔츠", max_quantity_per_product=10)
    other_group = OptionGroup.objects.create(product=non_ticket_product, name="모자", max_quantity_per_product=10)
    opt_a = group.options.create(name="A")
    opt_b = group.options.create(name="B")
    other_opt = other_group.options.create(name="O")

    for option in (opt_a, opt_b):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="paid"),
            product=non_ticket_product,
            price=non_ticket_product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=option
        )
    other_group_opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="paid"),
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=other_group_opr, product_option_group=other_group, product_option=other_opt
    )
    other_user_opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="paid"),
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=other_user_opr, product_option_group=group, product_option=opt_a
    )

    assert group.get_user_taken_stock_count(user=customer_user, include_cart=False, include_purchased=True) == 2


@pytest.mark.django_db
def test_product_rejects_when_single_option_cart_count_exceeds_leftover_stock(customer_user, non_ticket_product):
    # 단건 case — cart 에 이미 동일 option 1건 + 이번 1건 = 2 > leftover=1 → product-level 합산 검증이 거절.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", stock=1)
    cart_opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=non_ticket_product,
        price=non_ticket_product.price,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=cart_opr, product_option_group=group, product_option=opt
    )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(
                    non_ticket_product.name, opt.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.parametrize(
    ("mode", "purchased_count", "cart_count"),
    [
        # ADD: cart + purchased + 1 > max → 거절. 1 cart + 0 purchased + 1 new = 2 > max=1.
        (OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART, 0, 1),
        # CHECKOUT_SINGLE: cart 무시, purchased + 1 > max. 1 purchased + 1 = 2 > max=1.
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 1, 0),
        # CHECKOUT_CART: cart + purchased > max. 1 cart + 1 purchased = 2 > max=1.
        (OrderableCheckSerializerMode.CHECKOUT_CART, 1, 1),
    ],
)
@pytest.mark.django_db
def test_product_rejects_when_single_option_max_per_user_exceeded_per_mode(
    customer_user, non_ticket_product, mode, purchased_count, cart_count
):
    # 단건 case — 통합 검증이 mode 별 cart / purchased 분기를 단건도 처리하는지 검증.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", max_quantity_per_user=1)
    for _ in range(purchased_count):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="paid"),
            product=non_ticket_product,
            price=non_ticket_product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=opt
        )
    for _ in range(cart_count):
        opr = OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=non_ticket_product,
            price=non_ticket_product.price,
        )
        OrderProductOptionRelation.objects.create(
            order_product_relation=opr, product_option_group=group, product_option=opt
        )

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None},
            ],
        },
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    non_ticket_product.name, opt.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_same_option_submitted_more_than_leftover_stock(customer_user, non_ticket_product):
    # option stock=2 인데 같은 option 을 3번 제출 → option-level 의 +1 검사로는 통과하지만 합산 3 > 2 라서 product-level 에서 거절.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", stock=2)

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None}
                for _ in range(3)
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(
                    non_ticket_product.name, opt.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_rejects_when_same_option_submitted_more_than_max_per_user(customer_user, non_ticket_product):
    # max_quantity_per_user=2 인데 같은 option 을 3번 제출 → 합산 3 > 2 → 거절.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", max_quantity_per_user=2)

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None}
                for _ in range(3)
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": OptionNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    non_ticket_product.name, opt.name
                ),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_product_allows_same_option_within_aggregate_stock(customer_user, non_ticket_product):
    # stock=3, 합산 count=2 → 통과.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=10)
    opt = group.options.create(name="A", stock=3)

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
            "options": [
                {"product_option_group": str(group.id), "product_option": str(opt.id), "custom_response": None}
                for _ in range(2)
            ],
        },
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_product_rejects_when_option_group_max_quantity_exceeded(customer_user, non_ticket_product):
    # max_quantity_per_product=1, options=[2개] → 1 초과 → TOO_MUCH_OPTION.
    group = OptionGroup.objects.create(product=non_ticket_product, name="옵션", max_quantity_per_product=1)
    opt_a = group.options.create(name="A")
    opt_b = group.options.create(name="B")

    serializer = ProductOrderableCheckSerializer(
        data={
            "product": str(non_ticket_product.id),
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
                "detail": OptionGroupNotOrderableErrorMessages.TOO_MUCH_OPTION.format(
                    non_ticket_product.name, group.name
                ),
                "code": "invalid",
            },
        ],
    }
