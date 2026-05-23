import pytest
from core.util.testutil import errors_payload
from shop.order.imports import OrderProductImportSerializer
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import OptionGroup


@pytest.mark.django_db
def test_template_csv_includes_serializer_fields_and_option_group_names(product, option_group):
    csv = OrderProductImportSerializer.get_template_csv(product=product)
    header_line = csv.splitlines()[0]
    columns = [c.strip() for c in header_line.split(",")]
    assert columns == ["name", "phone", "email", "organization", "product_id", "donation_price", "사이즈"]


@pytest.mark.django_db
def test_import_create_persists_order_chain_with_paid_payment_history(customer_user, product, option_group):
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(product.id),
            "donation_price": 0,
            "사이즈": "M",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()

    assert opr.status == OrderProductRelation.OrderProductStatus.paid
    assert opr.price == product.price
    assert opr.order.user == customer_user
    assert CustomerInfo.objects.filter(order=opr.order, name="홍길동", email=customer_user.email).exists()
    assert OrderProductOptionRelation.objects.filter(
        order_product_relation=opr, product_option_group=option_group, product_option__name="M"
    ).exists()
    # imp_id 없는 결제 (CSV import 경유) — completed 상태로 기록되어 환불 불가.
    assert PaymentHistory.objects.filter(
        order=opr.order, imp_id=None, status=PaymentHistoryStatus.completed, price=opr.price
    ).exists()


@pytest.mark.django_db
def test_import_includes_option_additional_price_in_opr_price(customer_user, product, option_group):
    option_group.options.create(name="L", additional_price=1000)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(product.id),
            "donation_price": 0,
            "사이즈": "L",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.price == product.price + 1000


@pytest.mark.parametrize(
    ("override_email", "size_value", "expected_error"),
    [
        # CSV email 이 매칭되는 UserExt 없음 → validate 단계 1.
        ("nobody@example.com", "M", "User does not exists"),
        # 옵션 값이 그룹에 정의된 옵션명과 불일치 → validate 단계 2.
        (None, "XXL", "Invalid option: '사이즈' - XXL"),
    ],
)
@pytest.mark.django_db
def test_import_rejects_invalid_row_and_persists_nothing(
    customer_user, product, option_group, override_email, size_value, expected_error
):
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            # None 일 때 fixture user 매칭 — 옵션 검증 단계까지 도달.
            "email": override_email or customer_user.email,
            "organization": "",
            "product_id": str(product.id),
            "donation_price": 0,
            "사이즈": size_value,
        }
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"non_field_errors": [{"detail": expected_error, "code": "invalid"}]}
    # 어느 단계의 validation 실패든 atomic — Order / OPR / CustomerInfo 일체 미생성.
    assert not Order.objects.exists()
    assert not OrderProductRelation.objects.exists()
    assert not CustomerInfo.objects.exists()


@pytest.mark.django_db
def test_import_skips_option_group_column_when_csv_missing_it(customer_user, product, option_group):
    # option_group(name="사이즈") 존재 + CSV row 에 "사이즈" 컬럼 부재 → 해당 group 건너뜀 (OPR 옵션 0개).
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(product.id),
            "donation_price": 0,
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.options.count() == 0


@pytest.mark.django_db
def test_import_option_input_data_returns_empty_when_product_id_invalid():
    # `product_id` 가 DB 에 없는 UUID → cached_property `option_input_data` 가 [] 반환 (validate 진입 전 직접 접근 시).
    serializer = OrderProductImportSerializer(data={"product_id": "00000000-0000-0000-0000-000000000000"})
    assert serializer.option_input_data == []


@pytest.mark.django_db
def test_import_supports_custom_response_option_group(customer_user, product):
    custom_group = OptionGroup.objects.create(
        product=product, name="요청사항", is_custom_response=True, custom_response_pattern=r"^.*$"
    )
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(product.id),
            "donation_price": 0,
            "요청사항": "배송 빠르게",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert OrderProductOptionRelation.objects.filter(
        order_product_relation=opr, product_option_group=custom_group, custom_response="배송 빠르게"
    ).exists()
