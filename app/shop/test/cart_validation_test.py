from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import (
    CartNotOrderableErrorMessages,
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
    ProductNotOrderableErrorMessages,
    SignInErrorMessages,
    TagNotOrderableErrorMessages,
)
from core.util.testutil import errors_payload, pk_does_not_exist_error
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError
from rest_framework.fields import empty
from shop.order.models import (
    CustomerInfo,
    Order,
    OrderProductOptionRelation,
    OrderProductRelation,
    SingleProductCart,
)
from shop.product.models import OptionGroup, Product
from shop.serializers.cart_validation import (
    CartOrderableCheckSerializer,
    CustomerInfoCheckSerializer,
    OptionOrderableCheckSerializer,
    OrderableCheckSerializerMode,
    ProductOrderableCheckSerializer,
    SingleProductCartOrderableCheckSerializer,
    TagOrderableCheckSerializer,
)
from shop.test.helpers import make_serializer_context

_VALID_CUSTOMER_INFO = {
    "name": "홍길동",
    "phone": "010-1234-5678",
    "email": "buyer@example.com",
    "organization": "",
}


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


def test_option_group_property_returns_none_when_initial_data_missing():
    # initial_data 에 product_option_group 가 없으면 group property 는 None.
    serializer = OptionOrderableCheckSerializer(data={})
    assert serializer.group is None


@pytest.mark.django_db
def test_option_group_property_returns_instance_when_initial_data_holds_instance(option_group):
    # initial_data 가 OptionGroup 인스턴스를 직접 보유한 경우 (nested validation) — 그대로 반환.
    serializer = OptionOrderableCheckSerializer(data={"product_option_group": option_group})
    assert serializer.group == option_group


@pytest.mark.parametrize(
    "mode",
    [
        # leftover_stock 분기에서 ADD 외 mode 의 cart_count 보정 경로 (line 109-113) 진입.
        OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT,
        OrderableCheckSerializerMode.CHECKOUT_CART,
    ],
)
@pytest.mark.django_db
def test_option_leftover_stock_check_passes_in_non_add_modes(customer_user, option_group, option, mode):
    # stock > 0 + cart 없음 → CHECKOUT_* mode 에서도 leftover 검사 통과.
    option.stock = 1
    option.save()
    serializer = OptionOrderableCheckSerializer(
        data={
            "product_option_group": str(option_group.id),
            "product_option": str(option.id),
            "custom_response": None,
        },
        context=make_serializer_context(customer_user, mode=mode),
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
        data={"product": str(product.id), "options": [], "customer_info": _VALID_CUSTOMER_INFO},
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
        data={"product": str(product.id), "options": [], "customer_info": _VALID_CUSTOMER_INFO},
        context=make_serializer_context(customer_user, mode=OrderableCheckSerializerMode.ADD_SINGLE_PRODUCT_TO_CART),
    )
    assert serializer.validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT


@pytest.mark.parametrize(
    ("field", "value", "expected_detail", "expected_code"),
    [
        ("name", empty, "이 필드는 필수 항목입니다.", "required"),
        ("phone", empty, "이 필드는 필수 항목입니다.", "required"),
        ("email", empty, "이 필드는 필수 항목입니다.", "required"),
        ("organization", empty, "이 필드는 필수 항목입니다.", "required"),
        ("name", None, "이 필드는 null일 수 없습니다.", "null"),
        ("phone", None, "이 필드는 null일 수 없습니다.", "null"),
        ("email", None, "이 필드는 null일 수 없습니다.", "null"),
        ("organization", None, "이 필드는 null일 수 없습니다.", "null"),
        ("name", "", "이 필드는 blank일 수 없습니다.", "blank"),
        ("phone", "", "이 필드는 blank일 수 없습니다.", "blank"),
        ("email", "", "이 필드는 blank일 수 없습니다.", "blank"),
        ("phone", "01012345678", "이 값은 요구되는 패턴과 일치하지 않습니다.", "invalid"),
        ("email", "not-an-email", "유효한 이메일 주소를 입력하세요.", "invalid"),
    ],
)
def test_customer_info_field_rejections(field, value, expected_detail, expected_code):
    payload = {**_VALID_CUSTOMER_INFO}
    if value is empty:
        del payload[field]
    else:
        payload[field] = value
    serializer = CustomerInfoCheckSerializer(data=payload)
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        field: [{"detail": expected_detail, "code": expected_code}],
    }


def test_customer_info_allows_blank_organization_uniquely():
    # 4 필드 중 organization 만 allow_blank=True — 의도된 차이 (협회 미소속 사용자).
    serializer = CustomerInfoCheckSerializer(data={**_VALID_CUSTOMER_INFO, "organization": ""})
    assert serializer.is_valid()


def test_customer_info_passes_happy_path():
    serializer = CustomerInfoCheckSerializer(data=_VALID_CUSTOMER_INFO)
    assert serializer.is_valid()


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
def test_option_orderable_rejects_soft_deleted_group(customer_user, option_group):
    # validate_product_option 의 self.group 은 deleted_at 무관 lookup 이라 OPTION_NOT_SELECTED 가 부수 발생할 수
    # 있음 — is_custom_response=True 로 그 분기를 우회해 queryset 필터 단독 검증.
    option_group.is_custom_response = True
    option_group.custom_response_pattern = r"^.*$"
    option_group.save()
    option_group.delete()

    serializer = OptionOrderableCheckSerializer(
        data={"product_option_group": str(option_group.id), "product_option": None, "custom_response": None},
        context=make_serializer_context(customer_user),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"product_option_group": [pk_does_not_exist_error(option_group.id)]}


@pytest.mark.django_db
def test_option_rejects_when_option_soldout(customer_user, option_group, option, other_user):
    # option.stock=1, 다른 user 가 1건 paid → leftover=0 → option-level SOLDOUT.
    option.stock = 1
    option.save()
    OrderProductOptionRelation.objects.create(
        order_product_relation=OrderProductRelation.objects.create(
            order=Order.objects.create(user=other_user, name="other"),
            product=option_group.product,
            price=option_group.product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        ),
        product_option_group=option_group,
        product_option=option,
    )

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
        "product_option": [
            {
                "detail": OptionNotOrderableErrorMessages.SOLDOUT.format(option_group.product.name, option.name),
                "code": "invalid",
            },
        ],
    }


@pytest.mark.django_db
def test_option_rejects_when_cart_count_exceeds_leftover_stock(customer_user, option_group, option):
    # option.stock=1, 이미 cart 에 동일 option 1건 → ADD mode 에서 +1 = 2 > leftover=1 → TOO_MUCH_CART_OPTION.
    option.stock = 1
    option.save()
    OrderProductOptionRelation.objects.create(
        order_product_relation=OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="cart"),
            product=option_group.product,
            price=option_group.product.price,
        ),
        product_option_group=option_group,
        product_option=option,
    )

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
        "product_option": [
            {
                "detail": OptionNotOrderableErrorMessages.TOO_MUCH_CART_OPTION.format(
                    option_group.product.name, option.name
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
        # CHECKOUT_SINGLE_PRODUCT: cart 무시, purchased + 1 > max. 1 purchased + 1 = 2 > max=1.
        (OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT, 1, 0),
        # CHECKOUT_CART: cart + purchased > max. 1 cart + 1 purchased = 2 > max=1.
        (OrderableCheckSerializerMode.CHECKOUT_CART, 1, 1),
    ],
)
@pytest.mark.django_db
def test_option_rejects_when_max_quantity_per_user_exceeded(
    customer_user, option_group, option, mode, purchased_count, cart_count
):
    option.max_quantity_per_user = 1
    option.save()
    for _ in range(purchased_count):
        OrderProductOptionRelation.objects.create(
            order_product_relation=OrderProductRelation.objects.create(
                order=Order.objects.create(user=customer_user, name="paid"),
                product=option_group.product,
                price=option_group.product.price,
                status=OrderProductRelation.OrderProductStatus.paid,
            ),
            product_option_group=option_group,
            product_option=option,
        )
    for _ in range(cart_count):
        OrderProductOptionRelation.objects.create(
            order_product_relation=OrderProductRelation.objects.create(
                order=Order.objects.create(user=customer_user, name="cart"),
                product=option_group.product,
                price=option_group.product.price,
            ),
            product_option_group=option_group,
            product_option=option,
        )

    serializer = OptionOrderableCheckSerializer(
        data={
            "product_option_group": str(option_group.id),
            "product_option": str(option.id),
            "custom_response": None,
        },
        context=make_serializer_context(customer_user, mode=mode),
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "product_option": [
            {
                "detail": OptionNotOrderableErrorMessages.ALREADY_ORDERED_TOO_MUCH.format(
                    option_group.product.name, option.name
                ),
                "code": "invalid",
            },
        ],
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


@pytest.mark.django_db
def test_cart_validate_defensively_rejects_paid_cart(completed_order, customer_user):
    # 일반 flow 에서는 queryset filter (filter_has_no_payment_histories) 가 결제된 cart 를 PK lookup 단계에서 차단.
    # 본 분기는 validate() 가 lock 후 race 로 PaymentHistory 가 생긴 경우의 defensive 재검사 — 직접 validate() 호출.
    serializer = CartOrderableCheckSerializer(context=make_serializer_context(customer_user))
    with pytest.raises(ValidationError) as exc_info:
        serializer.validate({"cart": completed_order})
    assert exc_info.value.detail[0] == CartNotOrderableErrorMessages.ALREADY_ORDERED
