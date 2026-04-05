from __future__ import annotations

import typing

from core.const.tag import OpenAPITag
from core.models import MarkdownField
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.db.models.fields import TextField, URLField
from django.db.models.fields.files import FileField
from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.db.models.query import QuerySet
from drf_spectacular import openapi, types, utils
from modeltranslation.fields import TranslationField
from rest_framework import decorators, response, serializers, status, viewsets


class JsonSchemaViewSet(viewsets.GenericViewSet):
    def __new__(cls, *args: tuple, **kwargs: dict) -> JsonSchemaViewSet:
        if cls.serializer_class and not hasattr(cls.serializer_class, "get_json_schema"):
            raise TypeError(f"{cls.__name__} must have a serializer class with a 'get_json_schema' method.")

        return super().__new__(cls)

    @staticmethod
    def _get_choices_from_queryset(qs: QuerySet, is_nullable: bool) -> list[dict[str, str]]:
        choices: list[dict[str, str]] = [{"const": None, "title": "빈 값"}] if is_nullable else []

        related_model = qs.model
        if hasattr(related_model, "get_choices_queryset"):
            qs = related_model.get_choices_queryset()
        else:
            qs = qs.all()
            if hasattr(qs, "filter_active"):
                qs = qs.filter_active()
            elif hasattr(related_model, "is_active"):
                qs = qs.filter(is_active=True)

        for row in qs:
            choices.append({"const": str(row.pk), "title": str(row)})

        return choices

    @staticmethod
    def set_ui_schema(ui_schema: dict, field_name: str, data: dict) -> None:
        ui_schema.setdefault(field_name, {})
        ui_schema[field_name].update(data)

    def _get_related_field_info(self) -> list[tuple[str, object, serializers.Field, bool]]:
        """Returns list of (field_name, model_field, serializer_field, is_m2m) for FK/M2M fields."""
        serializer_class = typing.cast(type[JsonSchemaSerializer], self.get_serializer_class())

        if not hasattr(serializer_class.Meta, "model"):
            return []

        ser_fields: dict[str, serializers.Field] = serializer_class().fields
        model_fields = serializer_class.Meta.model._meta.fields
        model_m2m_fields = serializer_class.Meta.model._meta.many_to_many
        schema = serializer_class.get_json_schema()

        result = []
        for field in model_fields + model_m2m_fields:
            if field.name not in schema.get("properties", {}) or field.name not in ser_fields:
                continue

            serializer_field = ser_fields[field.name]

            if isinstance(field, ForeignKey):
                s_field = typing.cast(serializers.PrimaryKeyRelatedField | None, serializer_field)
                if not s_field or serializer_field.read_only:
                    continue
                result.append((field.name, field, serializer_field, False))
            elif isinstance(field, ManyToManyField):
                s_field = typing.cast(serializers.ManyRelatedField | None, serializer_field)
                if not s_field or serializer_field.read_only:
                    continue
                result.append((field.name, field, serializer_field, True))

        return result

    def get_choices(self) -> dict[str, list[dict[str, str]]]:
        choices: dict[str, list[dict[str, str]]] = {}

        for field_name, field, serializer_field, is_m2m in self._get_related_field_info():
            if is_m2m:
                qs = typing.cast(serializers.ManyRelatedField, serializer_field).child_relation.get_queryset()
                choices[field_name] = self._get_choices_from_queryset(qs, False)
            else:
                qs = typing.cast(serializers.PrimaryKeyRelatedField, serializer_field).get_queryset()
                choices[field_name] = self._get_choices_from_queryset(qs, field.null)

        return choices

    def get_json_schema(self) -> dict:  # noqa: C901
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
                    self.set_ui_schema(result["ui_schema"], field.name, {"ui:field": "m2m_select"})
                elif isinstance(field, FileField):
                    self.set_ui_schema(result["ui_schema"], field.name, {"ui:field": "file"})
                elif isinstance(field, URLField):
                    result["schema"]["properties"][field.name].pop("format", None)
                elif isinstance(field, TranslationField):
                    result["translation_fields"].add(field.translated_field.name)
                    if isinstance(field.translated_field, MarkdownField):
                        self.set_ui_schema(
                            result["ui_schema"], field.name, {"ui:widget": "textarea", "ui:field": "markdown"}
                        )
                    elif isinstance(field.translated_field, TextField):
                        self.set_ui_schema(result["ui_schema"], field.name, {"ui:widget": "textarea"})
                elif isinstance(field, MarkdownField):
                    self.set_ui_schema(
                        result["ui_schema"], field.name, {"ui:widget": "textarea", "ui:field": "markdown"}
                    )
                elif isinstance(field, TextField):
                    self.set_ui_schema(result["ui_schema"], field.name, {"ui:widget": "textarea"})

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

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_JSON_SCHEMA],
        summary="Choices for related fields",
        responses={status.HTTP_200_OK: openapi.OpenApiResponse(response=types.OpenApiTypes.OBJECT)},
    )
    @decorators.action(detail=False, methods=["get"], url_path="choices")
    def response_choices(self, *args: tuple, **kwargs: dict) -> response.Response:
        return response.Response(data=self.get_choices())
