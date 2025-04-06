from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = "core.fields.UUIDAutoField"
    name = "user"
