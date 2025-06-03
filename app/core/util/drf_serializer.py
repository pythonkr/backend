from openapi_schema_to_json_schema import to_json_schema
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.serializers import Serializer


def extract_openapi_schema_from_serializer(serializer: Serializer) -> dict:
    return AutoSchema().map_serializer(serializer)


def extract_jsonschema_from_serializer(serializer: Serializer) -> dict:
    return to_json_schema(
        schema=extract_openapi_schema_from_serializer(serializer),
        options={"keepNotSupported": ["readOnly", "writeOnly"]},
    )
