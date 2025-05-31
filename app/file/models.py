import hashlib
import mimetypes

from core.models import BaseAbstractModel
from django.core.files.storage import storages
from django.db import models


class PublicFile(BaseAbstractModel):
    file = models.FileField(unique=True, null=False, blank=False, upload_to="public/", storage=storages["public"])
    mimetype = models.CharField(max_length=256, null=True, blank=False)
    hash = models.CharField(max_length=256, null=False, blank=False)
    size = models.BigIntegerField(null=False, blank=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["file"]), models.Index(fields=["mimetype"]), models.Index(fields=["hash"])]

    def __str__(self) -> str:
        return self.file.name

    def clean(self) -> None:
        # 파일의 해시값, 크기, mimetype을 계산하여 저장합니다.
        hash_md5 = hashlib.md5(usedforsecurity=False)
        file_pointer = self.file.open("rb")

        for chunk in iter(lambda: file_pointer.read(4096), b""):
            hash_md5.update(chunk)

        self.hash = hash_md5.hexdigest()
        self.size = self.file.size
        self.mimetype = mimetypes.guess_type(self.file.name)[0]
