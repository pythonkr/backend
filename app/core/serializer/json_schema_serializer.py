from __future__ import annotations

import typing

from core.util.drf_serializer import extract_jsonschema_from_serializer
from rest_framework import serializers


class JsonSchema(typing.TypedDict):
    type: str
    schema: str
    properties: dict[str, dict[str, typing.Any]]
    required: list[str]


class JsonSchemaSerializer:
    @classmethod
    def get_json_schema(cls: type[serializers.Serializer]) -> JsonSchema:
        return extract_jsonschema_from_serializer(cls())
