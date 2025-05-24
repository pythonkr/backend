from django.apps import AppConfig


class FileConfig(AppConfig):
    name = "file"

    def ready(self):
        from file.models import PublicFile
        from simple_history import register

        register(PublicFile)
