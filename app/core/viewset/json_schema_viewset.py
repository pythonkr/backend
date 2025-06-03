from __future__ import annotations

import typing

from core.const.tag import OpenAPITag
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from django.db.models.fields.files import FileField
from django.db.models.fields.related import ForeignKey
from drf_spectacular import openapi, types, utils
from modeltranslation.fields import TranslationField
from rest_framework import decorators, response, status, viewsets


class JsonSchemaViewSet(viewsets.GenericViewSet):
    def __new__(cls, *args: tuple, **kwargs: dict) -> JsonSchemaViewSet:
        if cls.serializer_class and not hasattr(cls.serializer_class, "get_json_schema"):
            raise TypeError(f"{cls.__name__} must have a serializer class with a 'get_json_schema' method.")

        return super().__new__(cls)

    def get_json_schema(self) -> dict:
        serializer_class = typing.cast(type[JsonSchemaSerializer], self.get_serializer_class())

        result = {
            "schema": serializer_class.get_json_schema(),
            "ui_schema": {},
            "translation_fields": set(),
        }

        nullable_fields = [
            k for k, v in serializer_class.get_json_schema()["properties"].items() if "null" in v.get("type", [])
        ]

        if hasattr(serializer_class.Meta, "model") and "properties" in result["schema"]:
            model_fields = serializer_class.Meta.model._meta.fields

            for field in model_fields:
                if isinstance(field, ForeignKey):
                    enum_values = []
                    row_qs = field.related_model.objects
                    if hasattr(row_qs, "filter_active"):
                        row_qs = row_qs.filter_active()
                    elif hasattr(field.related_model, "is_active"):
                        row_qs = row_qs.filter(is_active=True)

                    for row in row_qs:
                        enum_values.append({"id": row.pk, "name": str(row)})

                    if field.name in result["schema"]["properties"]:
                        result["schema"]["properties"][field.name]["enum"] = [e["id"] for e in enum_values] + (
                            [None] if field.null else []
                        )

                    result["ui_schema"][field.name] = {
                        "ui:options": {
                            "ui:widget": "select",
                            "enumNames": [f"{e['name']} <{e['id']}>" for e in enum_values]
                            + (["빈 값"] if field.name in nullable_fields else []),
                        }
                    }

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
