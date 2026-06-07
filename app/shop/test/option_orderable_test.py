import pytest
from core.const.shop_error_messages import (
    OptionGroupNotOrderableErrorMessages,
    OptionNotOrderableErrorMessages,
    SignInErrorMessages,
)
from core.util.testutil import errors_payload, pk_does_not_exist_error
from django.contrib.auth.models import AnonymousUser
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.product.models import OptionGroup
from shop.serializers.cart_validation import OptionOrderableCheckSerializer
from shop.test.helpers import make_serializer_context


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
def test_custom_response_rejects_when_pattern_mismatch(customer_user, ticket_product):
    # is_custom_response=True 그룹에 pattern 위배 응답.
    group = OptionGroup.objects.create(
        product=ticket_product,
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
