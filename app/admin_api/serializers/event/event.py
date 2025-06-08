from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from event.models import Event
from rest_framework import serializers


class EventAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = COMMON_ADMIN_FIELDS + ("organization", "name_ko", "name_en")
