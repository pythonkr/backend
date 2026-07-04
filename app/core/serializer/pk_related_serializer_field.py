from typing import Any

from rest_framework import serializers


class PrimaryKeyRelatedSerializerField(serializers.PrimaryKeyRelatedField):
    def __init__(self, *args: Any, serializer: type[serializers.BaseSerializer], **kwargs: Any) -> None:
        self.serializer = serializer
        super().__init__(*args, **kwargs)

    def use_pk_only_optimization(self) -> bool:
        return False

    def to_representation(self, value: Any) -> Any:
        return self.serializer(value, context=self.context).data
