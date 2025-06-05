from event.presentation.models import PresentationCategory, PresentationSpeaker, PresentationType
from modeltranslation.translator import TranslationOptions, register


@register(PresentationType)
class PresentationTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(PresentationCategory)
class PresentationCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(PresentationSpeaker)
class PresentationSpeakerTranslationOptions(TranslationOptions):
    fields = (
        "name",
        "biography",
    )
