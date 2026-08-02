import pytest
from core.util.django_orm import (
    apply_diff_to_model,
    get_diff_data_from_jsonized_models,
    model_to_identifier,
    model_to_jsonable_dict,
)
from django.utils.translation import override
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationCategoryRelation,
    PresentationSpeaker,
)
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


def test_apply_diff_to_model_ignores_reordered_reverse_relation(db):
    presentation = baker.make(Presentation)
    speakers = baker.make(PresentationSpeaker, presentation=presentation, _quantity=2)
    diff = {model_to_identifier(presentation): {"speakers": [model_to_identifier(s) for s in reversed(speakers)]}}

    apply_diff_to_model(diff)

    assert set(presentation.speakers.values_list("id", flat=True)) == {s.pk for s in speakers}


def test_apply_diff_to_model_rejects_member_change_on_non_nullable_reverse_relation(db):
    presentation = baker.make(Presentation)
    speakers = baker.make(PresentationSpeaker, presentation=presentation, _quantity=2)
    diff = {model_to_identifier(presentation): {"speakers": [model_to_identifier(speakers[0])]}}

    with pytest.raises(ValueError, match="speakers"):
        apply_diff_to_model(diff)

    assert presentation.speakers.count() == 2


def test_apply_diff_to_model_applies_many_to_many_members(db):
    presentation = baker.make(Presentation)
    old_category, new_category = baker.make(PresentationCategory, type=presentation.type, _quantity=2)
    baker.make(PresentationCategoryRelation, presentation=presentation, category=old_category)
    diff = {model_to_identifier(presentation): {"categories": [model_to_identifier(new_category)]}}

    apply_diff_to_model(diff)

    assert set(presentation.categories.values_list("id", flat=True)) == {new_category.pk}


def test_model_to_jsonable_dict_sorts_reverse_relation_identifiers(db):
    presentation = baker.make(Presentation)
    speakers = baker.make(PresentationSpeaker, presentation=presentation, _quantity=3)

    snapshot = model_to_jsonable_dict(presentation)["model_data"][model_to_identifier(presentation)]

    assert snapshot["speakers"] == sorted(model_to_identifier(speaker) for speaker in speakers)


def test_model_to_jsonable_dict_sorts_many_to_many_identifiers(db):
    presentation = baker.make(Presentation)
    categories = baker.make(PresentationCategory, type=presentation.type, _quantity=3)
    for category in categories:
        baker.make(PresentationCategoryRelation, presentation=presentation, category=category)

    snapshot = model_to_jsonable_dict(presentation)["model_data"][model_to_identifier(presentation)]

    assert snapshot["categories"] == sorted(model_to_identifier(category) for category in categories)


PRESENTATION_KEY = "mdl:presentation:presentation:7dee621b-c3bb-4404-9900-fd796b03a5a0"
SPEAKER_A = "mdl:presentation:presentationspeaker:aee66cdf-d110-43e5-904a-41b8a7910923"
SPEAKER_B = "mdl:presentation:presentationspeaker:1367c0d5-312e-4606-b143-7d5ebbdafee1"


def test_get_diff_data_ignores_reordered_relation_identifiers():
    asis = {PRESENTATION_KEY: {"speakers": [SPEAKER_B, SPEAKER_A]}}
    tobe = {PRESENTATION_KEY: {"speakers": [SPEAKER_A, SPEAKER_B]}}

    assert get_diff_data_from_jsonized_models(asis, tobe) == {}


def test_get_diff_data_detects_changed_relation_members():
    asis = {PRESENTATION_KEY: {"speakers": [SPEAKER_B]}}
    tobe = {PRESENTATION_KEY: {"speakers": [SPEAKER_A, SPEAKER_B]}}

    assert get_diff_data_from_jsonized_models(asis, tobe) == {PRESENTATION_KEY: {"speakers": [SPEAKER_A, SPEAKER_B]}}


def test_get_diff_data_keeps_order_significant_for_plain_lists():
    asis = {PRESENTATION_KEY: {"tags": ["b", "a"]}}
    tobe = {PRESENTATION_KEY: {"tags": ["a", "b"]}}

    assert get_diff_data_from_jsonized_models(asis, tobe) == {PRESENTATION_KEY: {"tags": ["a", "b"]}}
