from core.models import MarkdownField
from django.db.models.fields import TextField
from django.db.models.fields.files import FileField
from django.db.models.fields.related import ForeignKey, ManyToManyField
from modeltranslation.fields import TranslationField


def ui_hints_for_model_field(model_field: object) -> dict:
    hints: dict = {}

    if isinstance(model_field, (ForeignKey, ManyToManyField)):
        if meta_schema := getattr(model_field.related_model, "choices_meta_schema", None):
            hints["ui:options"] = {"choiceMetaSchema": meta_schema}

    if isinstance(model_field, ManyToManyField):
        return hints | {"ui:field": "m2m_select"}
    if isinstance(model_field, FileField):
        return {"ui:field": "file"}
    if isinstance(model_field, TranslationField):
        model_field = model_field.translated_field
    if isinstance(model_field, MarkdownField):  # MarkdownField 는 TextField 하위 → 먼저 검사
        return {"ui:widget": "textarea", "ui:field": "markdown"}
    if isinstance(model_field, TextField):
        return {"ui:widget": "textarea"}
    return hints
