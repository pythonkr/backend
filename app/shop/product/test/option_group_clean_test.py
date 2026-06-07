import pytest
from django.core.exceptions import ValidationError
from shop.product.models import OptionGroup


@pytest.mark.django_db
def test_clean_rejects_custom_response_group_without_pattern(ticket_product):
    # is_custom_response=True 면 pattern 이 admin 계약 — 빈 응답 허용은 ".*", 비공란 강제는 ".+" 등으로 명시해야 함.
    with pytest.raises(ValidationError) as exc_info:
        OptionGroup(
            product=ticket_product,
            name="custom",
            is_custom_response=True,
            custom_response_pattern=None,
        ).clean()
    assert exc_info.value.message_dict == {
        "custom_response_pattern": ["is_custom_response=True 일 때 custom_response_pattern 은 필수입니다."],
    }


@pytest.mark.django_db
def test_clean_passes_for_default_group(ticket_product):
    # is_custom_response=False (default) → 미라이즈만 검증 (super().clean() 도달 포함).
    OptionGroup(product=ticket_product, name="size").clean()


@pytest.mark.django_db
def test_clean_rejects_invalid_regex_pattern(ticket_product):
    # invalid regex 가 저장되면 주문/수정 validation 시 runtime error 가 나므로 admin 입력 단계에서 막는다.
    with pytest.raises(ValidationError) as exc_info:
        OptionGroup(
            product=ticket_product,
            name="custom",
            is_custom_response=True,
            custom_response_pattern="[unclosed",
        ).clean()
    assert "custom_response_pattern" in exc_info.value.message_dict


@pytest.mark.django_db
def test_clean_validates_pattern_even_when_is_custom_response_false(ticket_product):
    # 저장된 invalid pattern 은 향후 is_custom_response 토글 시 runtime error 의 원인이 된다 → 항상 검증.
    with pytest.raises(ValidationError) as exc_info:
        OptionGroup(
            product=ticket_product,
            name="custom",
            is_custom_response=False,
            custom_response_pattern="(",
        ).clean()
    assert "custom_response_pattern" in exc_info.value.message_dict
