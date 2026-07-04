from django import template
from django.utils.translation import get_language

register = template.Library()


@register.simple_tag
def is_english() -> bool:
    return (get_language() or "").lower().startswith("en")
