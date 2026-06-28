from event.models import Event
from rest_framework import serializers


class EventSerializer(serializers.ModelSerializer):
    logo = serializers.FileField(source="logo.file", read_only=True)

    class Meta:
        model = Event
        fields = ("id", "name", "logo", "slogan", "description", "event_start_at", "event_end_at")
