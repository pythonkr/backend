from rest_framework import serializers


class ReadOnlyModelSerializer(serializers.Serializer):
    def create(self, validated_data):
        raise NotImplementedError("This serializer does not support creation.")

    def update(self, instance, validated_data):
        raise NotImplementedError("This serializer does not support updates.")

    def save(self, **kwargs):
        raise NotImplementedError("This serializer does not support saving.")
