import pytest
from allauth.account.models import EmailAddress
from core.util.testutil import errors_payload
from shop.order.imports import OrderProductImportSerializer
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import OptionGroup
from user.models import UserExt


@pytest.mark.django_db
def test_template_csv_includes_serializer_fields_and_option_group_names(ticket_product, option_group):
    csv = OrderProductImportSerializer.get_template_csv(product=ticket_product)
    header_line = csv.splitlines()[0]
    columns = [c.strip() for c in header_line.split(",")]
    assert columns == ["name", "phone", "email", "organization", "product_id", "donation_price", "사이즈"]


@pytest.mark.django_db
def test_import_create_persists_order_chain_with_paid_payment_history(customer_user, ticket_product, option_group):
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
            "사이즈": "M",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()

    assert opr.status == OrderProductRelation.OrderProductStatus.paid
    assert opr.price == ticket_product.price
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
def test_import_includes_option_additional_price_in_opr_price(customer_user, ticket_product, option_group):
    option_group.options.create(name="L", additional_price=1000)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
            "사이즈": "L",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert opr.price == ticket_product.price + 1000


@pytest.mark.django_db
def test_import_rejects_invalid_row_and_persists_nothing(customer_user, ticket_product, option_group):
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
            # 옵션 값이 그룹에 정의된 옵션명과 불일치.
            "사이즈": "XXL",
        }
    )
    assert serializer.is_valid() is False
    expected_error = "Invalid option: '사이즈' - XXL"
    assert errors_payload(serializer.errors) == {"non_field_errors": [{"detail": expected_error, "code": "invalid"}]}
    # validation 실패 시 Order / OPR / CustomerInfo 일체 미생성. 유저 생성도 옵션 검증 이후라 발생하지 않음.
    assert not Order.objects.exists()
    assert not OrderProductRelation.objects.exists()
    assert not CustomerInfo.objects.exists()
    assert not UserExt.objects.filter(email="홍길동").exists()


@pytest.mark.django_db
def test_import_creates_user_when_email_matches_no_account(ticket_product):
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": "nobody@example.com",
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
        }
    )
    assert serializer.is_valid(), serializer.errors
    opr = serializer.save()

    created = UserExt.objects.get(email="nobody@example.com")
    assert opr.order.user == created
    assert created.nickname_ko == created.nickname_en == "홍길동"
    # 비밀번호 미설정 — 본인이 비밀번호 재설정 / 소셜 로그인으로 계정을 이어받는다.
    assert not created.has_usable_password()
    assert EmailAddress.objects.filter(user=created, email="nobody@example.com", verified=True, primary=True).exists()


@pytest.mark.django_db
def test_import_matches_user_by_secondary_email_address(customer_user, ticket_product):
    EmailAddress.objects.create(user=customer_user, email="alt@example.com", verified=True)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": "alt@example.com",
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
        }
    )
    assert serializer.is_valid(), serializer.errors
    opr = serializer.save()

    assert opr.order.user == customer_user
    assert UserExt.objects.count() == 1


@pytest.mark.django_db
def test_import_resolves_merged_account_to_merge_target(customer_user, other_user, ticket_product):
    # 병합된 소스 계정에 남은 이메일로 들어와도 주문은 병합 대상 계정에 붙어야 한다.
    EmailAddress.objects.create(user=other_user, email="merged@example.com", verified=True)
    other_user.merged_to = customer_user
    other_user.is_active = False
    other_user.save(update_fields=["merged_to", "is_active"])

    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": "merged@example.com",
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().order.user == customer_user


@pytest.mark.django_db
def test_import_skips_option_group_column_when_csv_missing_it(customer_user, ticket_product, option_group):
    # option_group(name="사이즈") 존재 + CSV row 에 "사이즈" 컬럼 부재 → 해당 group 건너뜀 (OPR 옵션 0개).
    option_group.options.create(name="M", additional_price=0)
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(ticket_product.id),
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
def test_import_supports_custom_response_option_group(customer_user, ticket_product):
    custom_group = OptionGroup.objects.create(
        product=ticket_product, name="요청사항", is_custom_response=True, custom_response_pattern=r"^.*$"
    )
    serializer = OrderProductImportSerializer(
        data={
            "name": "홍길동",
            "phone": "010-1234-5678",
            "email": customer_user.email,
            "organization": "",
            "product_id": str(ticket_product.id),
            "donation_price": 0,
            "요청사항": "배송 빠르게",
        }
    )
    assert serializer.is_valid()
    opr = serializer.save()
    assert OrderProductOptionRelation.objects.filter(
        order_product_relation=opr, product_option_group=custom_group, custom_response="배송 빠르게"
    ).exists()
