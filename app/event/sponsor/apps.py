import importlib

from django.apps import AppConfig


class SponsorConfig(AppConfig):
    name = "event.sponsor"

    def ready(self):
        importlib.import_module("event.sponsor.translation")

        from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
        from simple_history import register

        register(SponsorTier)
        register(SponsorTag)
        register(Sponsor, excluded_fields=["logo_ko", "logo_en"])
