import importlib

from django.apps import AppConfig


class OrderConfig(AppConfig):
    name = "shop.order"

    def ready(self):
        importlib.import_module("shop.order.translation")
