from modeltranslation.translator import TranslationOptions, register
from user.models.organization import Organization
from user.models.user import UserExt


@register(UserExt)
class UserExtTranslationOptions(TranslationOptions):
    fields = ("nickname",)


@register(Organization)
class OrganizationTranslationOptions(TranslationOptions):
    fields = ("name",)
