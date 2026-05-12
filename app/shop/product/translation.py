from modeltranslation.translator import TranslationOptions, register
from shop.product.models import Option, OptionGroup, Product, Tag
from simple_history import register as history_register


@register(Tag)
class TagTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(OptionGroup)
class OptionGroupTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Option)
class OptionTranslationOptions(TranslationOptions):
    fields = ("name",)


history_register(Tag)
history_register(Product)
history_register(OptionGroup)
history_register(Option)
