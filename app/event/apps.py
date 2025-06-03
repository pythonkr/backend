import importlib

from django.apps import AppConfig


class EventConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "event"

    def ready(self):
        importlib.import_module("event.translation")

        from event.models import Event
        from simple_history import register

        register(Event)
