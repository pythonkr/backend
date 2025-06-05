from modeltranslation.translator import TranslationOptions, register
from user.models import Organization


@register(Organization)
class OrganizationTranslationOptions(TranslationOptions):
    fields = ("name",)
