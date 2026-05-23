from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import OptionGroupNotModifiableErrorMessages
from core.util.testutil import errors_payload, pk_does_not_exist_error
from freezegun import freeze_time
from shop.order.models import OrderProductOptionRelation, OrderProductRelation
from shop.order.serializers.validator import OptionProductOptionCustomResponseModifyRequestSerializer
from shop.product.models import OptionGroup


@pytest.fixture
def paid_custom_option_relation(product, order_factory):
    completed_order = order_factory(status="completed")
    """결제 완료된 OPR 의 custom_response 옵션 — 수정 가능 그룹 (response_modifiable_ends_at 미래)."""
    group = OptionGroup.objects.create(
        product=product,
        name="추가 요청사항",
        is_custom_response=True,
        custom_response_pattern=r"^.{1,100}$",
        response_modifiable_ends_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )
    return OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="initial",
    )


@pytest.mark.django_db
def test_modify_rejects_when_relation_belongs_to_different_order_product(paid_custom_option_relation, order_factory):
    completed_order = order_factory(status="completed")
    other_opr = OrderProductRelation.objects.create(
        order=completed_order,
        product=completed_order.products.first().product,
        price=0,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(paid_custom_option_relation.id), "custom_response": "ok"},
        context={"order_product_rel": other_opr},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": OptionGroupNotModifiableErrorMessages.ORDER_PRODUCT_OPTION_RELATION_MISMATCH, "code": "invalid"},
        ],
    }


@pytest.mark.django_db
def test_modify_rejects_when_response_modifiable_ends_at_is_none(product, order_factory):
    completed_order = order_factory(status="completed")
    group = OptionGroup.objects.create(
        product=product,
        name="lock",
        is_custom_response=True,
        custom_response_pattern=r"^.*$",
    )
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="x",
    )
    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(rel.id), "custom_response": "y"},
        context={"order_product_rel": rel.order_product_relation},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": OptionGroupNotModifiableErrorMessages.RESPONSE_NOT_MODIFIABLE, "code": "invalid"}
        ],
    }


@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))  # fixture 의 ends_at(2099) 지남.
@pytest.mark.django_db
def test_modify_rejects_when_modifiable_deadline_passed(paid_custom_option_relation):
    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(paid_custom_option_relation.id), "custom_response": "ok"},
        context={"order_product_rel": paid_custom_option_relation.order_product_relation},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": OptionGroupNotModifiableErrorMessages.RESPONSE_MODIFIABLE_ENDS_AT, "code": "invalid"},
        ],
    }


@pytest.mark.django_db
def test_modify_rejects_when_custom_response_pattern_mismatch(product, order_factory):
    completed_order = order_factory(status="completed")
    group = OptionGroup.objects.create(
        product=product,
        name="numeric",
        is_custom_response=True,
        custom_response_pattern=r"^\d{6}$",
        response_modifiable_ends_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="000000",
    )

    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(rel.id), "custom_response": "abc"},
        context={"order_product_rel": rel.order_product_relation},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": OptionGroupNotModifiableErrorMessages.CUSTOM_RESPONSE_PATTERN_MISMATCH, "code": "invalid"},
        ],
    }


@pytest.mark.django_db
def test_modify_save_persists_new_custom_response(paid_custom_option_relation):
    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(paid_custom_option_relation.id), "custom_response": "updated"},
        context={"order_product_rel": paid_custom_option_relation.order_product_relation},
    )
    assert serializer.is_valid()

    serializer.save()

    paid_custom_option_relation.refresh_from_db()
    assert paid_custom_option_relation.custom_response == "updated"


@pytest.mark.django_db
def test_modify_rejects_refunded_opr_option_via_queryset_filter(paid_custom_option_relation):
    # OPR status 를 refunded 로 변경 → queryset 의 status=paid 필터에서 빠짐 → PK 매칭 0건.
    opr = paid_custom_option_relation.order_product_relation
    opr.status = OrderProductRelation.OrderProductStatus.refunded
    opr.save()

    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(paid_custom_option_relation.id), "custom_response": "x"},
        context={"order_product_rel": opr},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "order_product_option_relation": [pk_does_not_exist_error(paid_custom_option_relation.id)],
    }


@pytest.mark.django_db
def test_modify_rejects_non_custom_response_group_option_via_queryset_filter(product, order_factory):
    completed_order = order_factory(status="completed")
    plain_group = OptionGroup.objects.create(product=product, name="plain", is_custom_response=False)
    rel = OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=plain_group,
    )

    serializer = OptionProductOptionCustomResponseModifyRequestSerializer(
        data={"order_product_option_relation": str(rel.id), "custom_response": "x"},
        context={"order_product_rel": rel.order_product_relation},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "order_product_option_relation": [pk_does_not_exist_error(rel.id)],
    }
