from event.models import Event
from modeltranslation.translator import TranslationOptions, register


@register(Event)
class EventTranslationOptions(TranslationOptions):
    fields = ("name", "slogan", "description")
