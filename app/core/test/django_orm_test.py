import pytest
from core.util.django_orm import apply_diff_to_model, model_to_identifier
from django.utils.translation import override
from event.presentation.models import Presentation
from model_bakery import baker


@pytest.mark.parametrize("active_language", ["ko", "en"], ids=["applied_in_ko", "applied_in_en"])
def test_apply_diff_to_model_ignores_translated_original_field(db, active_language):
    presentation = baker.make(Presentation, title_ko="한글제목", title_en="EnglishTitle")
    diff = {model_to_identifier(presentation): {"title": "NewEnglishTitle", "title_en": "NewEnglishTitle"}}

    with override(active_language):
        apply_diff_to_model(diff)

    presentation.refresh_from_db()
    assert presentation.title_en == "NewEnglishTitle"
    assert presentation.title_ko == "한글제목"


def test_apply_diff_to_model_applies_plain_field(db):
    presentation = baker.make(Presentation, slideshow_url="https://example.com/old")
    diff = {model_to_identifier(presentation): {"slideshow_url": "https://example.com/new"}}

    apply_diff_to_model(diff)

    presentation.refresh_from_db()
    assert presentation.slideshow_url == "https://example.com/new"
