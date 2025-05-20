import importlib

from django.apps import AppConfig


class FileConfig(AppConfig):
    name = "file"

    def ready(self):
        importlib.import_module("file.translations")

        from file.models import PublicFile
        from simple_history import register

        register(PublicFile)
