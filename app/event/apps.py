import importlib

from django.apps import AppConfig


class EventConfig(AppConfig):
    name = "event"

    def ready(self):
        importlib.import_module("event.translation")

        from event.models import Event
        from simple_history import register

        register(Event)
