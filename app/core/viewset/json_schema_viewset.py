from __future__ import annotations

import typing

from core.const.tag import OpenAPITag
from core.openapi.ui_hints import ui_hints_for_model_field
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.db.models.fields import URLField
from django.db.models.fields.related import ForeignKey, ManyToManyField
from drf_spectacular import openapi, types, utils
from modeltranslation.fields import TranslationField
from rest_framework import decorators, response, serializers, status, viewsets


class JsonSchemaMixin(viewsets.GenericViewSet):
    def __new__(cls, *args: tuple, **kwargs: dict) -> JsonSchemaMixin:
        if cls.serializer_class and not hasattr(cls.serializer_class, "get_json_schema"):
            raise TypeError(f"{cls.__name__} must have a serializer class with a 'get_json_schema' method.")

        return super().__new__(cls)

    @staticmethod
    def set_ui_schema(ui_schema: dict, field_name: str, data: dict) -> None:
        ui_schema.setdefault(field_name, {})
        ui_schema[field_name].update(data)

    def get_json_schema(self) -> dict:
        serializer_class = typing.cast(type[JsonSchemaSerializer], self.get_serializer_class())

        result = {
            "schema": serializer_class.get_json_schema(),
            "ui_schema": {},
            "translation_fields": set(),
        }

        for schema_field in result["schema"]["properties"].values():
            if "pattern" in schema_field:
                # Remove the pattern as python regex is not well compatible with javaScript regex.
                # TODO: FIXME: Add a compatibility layer for regex patterns.
                schema_field.pop("pattern", None)

        if hasattr(serializer_class.Meta, "model") and "properties" in result["schema"]:
            ser_fields: dict[str, serializers.Field] = serializer_class().fields
            model_fields = serializer_class.Meta.model._meta.fields
            model_m2m_fields = serializer_class.Meta.model._meta.many_to_many

            for field in model_fields + model_m2m_fields:
                if field.name not in result["schema"]["properties"] or field.name not in ser_fields:
                    continue

                serializer_field = ser_fields[field.name]

                if isinstance(field, ForeignKey):
                    if not typing.cast(serializers.PrimaryKeyRelatedField | None, serializer_field):
                        continue
                    if serializer_field.read_only:
                        continue
                elif isinstance(field, ManyToManyField):
                    if not typing.cast(serializers.ManyRelatedField | None, serializer_field):
                        continue
                    if serializer_field.read_only:
                        continue
                    result["schema"]["properties"][field.name]["uniqueItems"] = True
                elif isinstance(field, URLField):
                    result["schema"]["properties"][field.name].pop("format", None)
                elif isinstance(field, TranslationField):
                    result["translation_fields"].add(field.translated_field.name)

                if hints := ui_hints_for_model_field(field):
                    self.set_ui_schema(result["ui_schema"], field.name, hints)

        result["translation_fields"] = list(result["translation_fields"])
        return result

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_JSON_SCHEMA],
        summary="JSON Schema",
        responses={status.HTTP_200_OK: openapi.OpenApiResponse(response=types.OpenApiTypes.OBJECT)},
    )
    @decorators.action(detail=False, methods=["get"], url_path="json-schema")
    def response_json_schema(self, *args: tuple, **kwargs: dict) -> response.Response:
        return response.Response(data=self.get_json_schema())
