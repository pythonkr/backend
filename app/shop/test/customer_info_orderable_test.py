import pytest
from core.util.testutil import errors_payload
from rest_framework.fields import empty
from shop.serializers.cart_validation import CustomerInfoCheckSerializer


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
    payload = {"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""}
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
    serializer = CustomerInfoCheckSerializer(
        data={"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""}
    )
    assert serializer.is_valid()


def test_customer_info_passes_happy_path():
    serializer = CustomerInfoCheckSerializer(
        data={"name": "홍길동", "phone": "010-1234-5678", "email": "buyer@example.com", "organization": ""}
    )
    assert serializer.is_valid()
