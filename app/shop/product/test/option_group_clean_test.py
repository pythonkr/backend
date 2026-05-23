import pytest
from django.core.exceptions import ValidationError
from shop.product.models import OptionGroup


@pytest.mark.django_db
def test_clean_rejects_custom_response_group_without_pattern(product):
    # is_custom_response=True 면 pattern 이 admin 계약 — 빈 응답 허용은 ".*", 비공란 강제는 ".+" 등으로 명시해야 함.
    with pytest.raises(ValidationError) as exc_info:
        OptionGroup(
            product=product,
            name="custom",
            is_custom_response=True,
            custom_response_pattern=None,
        ).clean()
    assert exc_info.value.message_dict == {
        "custom_response_pattern": ["is_custom_response=True 일 때 custom_response_pattern 은 필수입니다."],
    }


@pytest.mark.django_db
def test_clean_passes_for_default_group(product):
    # is_custom_response=False (default) → 미라이즈만 검증 (super().clean() 도달 포함).
    OptionGroup(product=product, name="size").clean()
