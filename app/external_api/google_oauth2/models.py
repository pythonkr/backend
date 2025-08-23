from core.models import BaseAbstractModel
from django.db import models


class GoogleOAuth2(BaseAbstractModel):
    refresh_token = models.CharField(max_length=512)
