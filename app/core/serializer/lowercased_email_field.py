from rest_framework import serializers


class LowercasedEmailField(serializers.EmailField):
    def to_internal_value(self, data: str) -> str:
        return super().to_internal_value(data).lower()
