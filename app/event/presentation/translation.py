from event.presentation.models import Presentation, PresentationCategory, PresentationSpeaker, PresentationType, Room
from modeltranslation.translator import TranslationOptions, register


@register(PresentationType)
class PresentationTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(PresentationCategory)
class PresentationCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Presentation)
class PresentationTranslationOptions(TranslationOptions):
    fields = ("title", "summary", "description")


@register(PresentationSpeaker)
class PresentationSpeakerTranslationOptions(TranslationOptions):
    fields = ("biography",)


@register(Room)
class RoomTranslationOptions(TranslationOptions):
    fields = ("name",)
