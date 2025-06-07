from event.sponsor.models import Sponsor, SponsorTier
from modeltranslation.translator import TranslationOptions, register


@register(SponsorTier)
class SponsorTierTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Sponsor)
class SponsorTranslationOptions(TranslationOptions):
    fields = ("name", "description")
