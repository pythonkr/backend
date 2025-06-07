from modeltranslation.translator import TranslationOptions, register
from user.models.organization import Organization


@register(Organization)
class OrganizationTranslationOptions(TranslationOptions):
    fields = ("name",)
