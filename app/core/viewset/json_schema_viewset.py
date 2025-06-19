from __future__ import annotations

import functools
import typing

from core.const.tag import OpenAPITag
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.db.models.base import Model
from django.db.models.fields.files import FileField
from django.db.models.fields.related import ForeignKey, ManyToManyField
from drf_spectacular import openapi, types, utils
from modeltranslation.fields import TranslationField
from rest_framework import decorators, response, status, viewsets


class JsonSchemaViewSet(viewsets.GenericViewSet):
    def __new__(cls, *args: tuple, **kwargs: dict) -> JsonSchemaViewSet:
        if cls.serializer_class and not hasattr(cls.serializer_class, "get_json_schema"):
            raise TypeError(f"{cls.__name__} must have a serializer class with a 'get_json_schema' method.")

        return super().__new__(cls)

    @staticmethod
    @functools.lru_cache
    def get_enum_values(model: Model, is_nullable: bool) -> list[dict[str, str]]:
        enum_values: list[dict[str, str]] = [{"const": None, "title": "빈 값"}] if is_nullable else []

        if hasattr(model, "objects"):
            qs = model.objects.all()
            if hasattr(qs, "filter_active"):
                qs = qs.filter_active()
            elif hasattr(model, "is_active"):
                qs = qs.filter(is_active=True)

            for row in list(qs):
                enum_values.append({"const": str(row.pk), "title": str(row)})

        return enum_values

    def get_json_schema(self) -> dict:
        serializer_class = typing.cast(type[JsonSchemaSerializer], self.get_serializer_class())

        result = {
            "schema": serializer_class.get_json_schema(),
            "ui_schema": {},
            "translation_fields": set(),
        }

        if hasattr(serializer_class.Meta, "model") and "properties" in result["schema"]:
            model_fields = serializer_class.Meta.model._meta.fields
            model_m2m_fields = serializer_class.Meta.model._meta.many_to_many

            for field in model_fields + model_m2m_fields:
                if field.name not in result["schema"]["properties"]:
                    continue

                if isinstance(field, ForeignKey):
                    e_values = self.get_enum_values(field.related_model, field.null)
                    result["schema"]["properties"][field.name]["oneOf"] = e_values
                elif isinstance(field, ManyToManyField):
                    e_values = self.get_enum_values(field.related_model, False)
                    result["schema"]["properties"][field.name]["items"]["oneOf"] = e_values
                    result["schema"]["properties"][field.name]["uniqueItems"] = True
                    result["ui_schema"][field.name] = {"ui:field": "m2m_select"}
                elif isinstance(field, FileField):
                    result["ui_schema"][field.name] = {"ui:field": "file"}
                elif isinstance(field, TranslationField):
                    result["translation_fields"].add(field.translated_field.name)

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
