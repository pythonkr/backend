from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
from modeltranslation.translator import TranslationOptions, register


@register(SponsorTier)
class SponsorTierTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(SponsorTag)
class SponsorTagTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Sponsor)
class SponsorTranslationOptions(TranslationOptions):
    fields = ("name",)
