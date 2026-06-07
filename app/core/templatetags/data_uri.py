import base64
import mimetypes
from functools import lru_cache

from django import template
from django.conf import settings

register = template.Library()


@register.filter
@lru_cache(maxsize=None)
def data_uri(path: str) -> str:
    file = settings.BASE_DIR / path
    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode('ascii')}"
