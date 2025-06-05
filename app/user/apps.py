import importlib

from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "user"

    def ready(self):
        importlib.import_module("user.translation")

        from simple_history import register
        from user.models import Organization, UserExt

        register(UserExt)
        register(Organization)
