from core.models import BaseAbstractModel
from django.core.files.storage import storages
from django.db import models


class PublicFile(BaseAbstractModel):
    file = models.FileField(unique=True, null=False, blank=False, upload_to="public/", storage=storages["public"])
    alternate_text = models.TextField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["-created_at"]
