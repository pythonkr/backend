import importlib

from django.apps import AppConfig


class CmsConfig(AppConfig):
    name = "cms"

    def ready(self):
        importlib.import_module("cms.translation")

        from cms.models import Page, Section, Sitemap
        from simple_history import register

        register(Page)
        register(Sitemap)
        register(Section)
