from file.models import PublicFile
from modeltranslation.translator import TranslationOptions, register


@register(PublicFile)
class PublicFileTranslationOptions(TranslationOptions):
    fields = ("alternate_text",)
