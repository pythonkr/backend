import importlib

from django.apps import AppConfig


class ProductConfig(AppConfig):
    name = "shop.product"

    def ready(self):
        importlib.import_module("shop.product.translation")
