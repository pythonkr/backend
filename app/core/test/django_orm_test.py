"""core.util.django_orm 의 diff 적용 헬퍼 테스트."""

import pytest
from core.util.django_orm import apply_diff_to_model, model_to_identifier, translated_original_field_names
from django.utils.translation import override
from event.presentation.models import Presentation
from file.models import PublicFile
from model_bakery import baker
from user.models import UserExt


def test_translated_original_field_names_returns_registered_fields():
    """modeltranslation 에 등록된 원본 필드명을 돌려준다."""
    assert translated_original_field_names(UserExt) == {"nickname"}
    assert translated_original_field_names(Presentation) == {"title", "summary", "description"}


def test_translated_original_field_names_is_empty_for_unregistered_model():
    """번역 등록이 없는 모델은 빈 집합을 돌려준다."""
    assert translated_original_field_names(PublicFile) == set()


@pytest.mark.parametrize("active_language", ["ko", "en"], ids=["applied_in_ko", "applied_in_en"])
def test_apply_diff_to_model_ignores_translated_original_field(db, active_language):
    """원본 필드(title)는 활성 언어에 따라 라우팅되므로 무시하고, 언어별 컬럼만 적용해야 한다."""
    presentation = baker.make(Presentation, title_ko="한글제목", title_en="EnglishTitle")
    diff = {model_to_identifier(presentation): {"title": "NewEnglishTitle", "title_en": "NewEnglishTitle"}}

    with override(active_language):
        apply_diff_to_model(diff)

    presentation.refresh_from_db()
    assert presentation.title_en == "NewEnglishTitle"
    assert presentation.title_ko == "한글제목"


def test_apply_diff_to_model_applies_plain_field(db):
    """번역 대상이 아닌 필드는 그대로 적용한다."""
    presentation = baker.make(Presentation, slideshow_url="https://example.com/old")
    diff = {model_to_identifier(presentation): {"slideshow_url": "https://example.com/new"}}

    apply_diff_to_model(diff)

    presentation.refresh_from_db()
    assert presentation.slideshow_url == "https://example.com/new"
