from typing import ClassVar

from core.util.testutil import ModelApiFixture
from django.urls import reverse


class DocumentApi(ModelApiFixture):
    name: ClassVar[str] = "v1:document"

    def download(self, pk):
        return self.http_client.get(reverse(f"{self.name}-download", kwargs={"pk": pk}))

    def verify(self, token):
        return self.http_client.get(reverse("v1:certificate-verify", kwargs={"token": token}))
