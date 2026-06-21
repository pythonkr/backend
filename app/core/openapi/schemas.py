from core.openapi.filter_extension import DjangoFilterExtension  # noqa: F401  drf-spectacular 확장 등록
from core.openapi.ui_hints import ui_hints_for_model_field
from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import ForeignKey, ManyToManyField
from drf_spectacular.openapi import AutoSchema, OpenApiExample, OpenApiResponse
from drf_spectacular.utils import OpenApiParameter
from modeltranslation.fields import TranslationField
from rest_framework import status

HTML_EXAMPLE_STR = "<!DOCTYPE html><html><body><img src='data:image/png;base64, ...'></body></html>"


class BackendAutoSchema(AutoSchema):
    global_params = [
        OpenApiParameter(
            name="Accept-Language", location=OpenApiParameter.HEADER, description="`ko` or `en`. Default value is `ko`"
        )
    ]

    def get_override_parameters(self) -> list[OpenApiParameter]:
        return super().get_override_parameters() + self.global_params

    def _map_serializer_field(self, field, direction, bypass_extensions=False):
        schema = super()._map_serializer_field(field, direction, bypass_extensions)
        if isinstance(schema, dict) and "$ref" not in schema and (model_field := self._model_field_for(field)):
            schema = {**schema, **self._model_field_extensions(model_field)}
        return schema

    @staticmethod
    def _model_field_extensions(model_field) -> dict:
        ext: dict = {}
        if hints := ui_hints_for_model_field(model_field):
            ext["x-ui-schema"] = hints
        if isinstance(model_field, TranslationField):
            ext["x-translation"] = {"of": model_field.translated_field.name, "language": model_field.language}
        if isinstance(model_field, ForeignKey | ManyToManyField):
            ext["x-relation"] = {
                "model": model_field.related_model.__name__,
                "many": isinstance(model_field, ManyToManyField),
            }
        if isinstance(model_field, ManyToManyField):
            ext["uniqueItems"] = True
        return ext

    @staticmethod
    def _model_field_for(field):
        model = getattr(getattr(field.parent, "Meta", None), "model", None)
        source = getattr(field, "source", None) or getattr(field, "field_name", None)
        if model is None or not source or "." in source or source == "*":
            return None
        try:
            return model._meta.get_field(source)
        except FieldDoesNotExist:
            return None


def build_html_responses(names: list[str], status_code: int = status.HTTP_200_OK) -> dict[int, OpenApiResponse]:
    examples = [
        OpenApiExample(
            name=name,
            media_type="text/html",
            value=HTML_EXAMPLE_STR,
            status_codes=[status_code],
        )
        for name in names
    ]
    return {status_code: OpenApiResponse(response=str, examples=examples)}
