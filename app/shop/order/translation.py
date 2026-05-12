from modeltranslation.translator import TranslationOptions, register
from shop.order.models import Order
from simple_history import register as history_register


@register(Order)
class OrderTranslationOptions(TranslationOptions):
    fields = ("name",)


history_register(Order)
