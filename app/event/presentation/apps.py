import importlib

from django.apps import AppConfig


class PresentationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "event.presentation"

    def ready(self):
        importlib.import_module("event.presentation.translation")

        from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType
        from simple_history import register

        register(PresentationType)
        register(PresentationCategory)
        register(Presentation)
        register(PresentationSpeaker)
