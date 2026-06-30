from typing import ClassVar
from urllib.parse import urlencode

from core.util.testutil import ModelApiFixture
from django.urls import reverse


class OrdersAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-order"

    def refund(self, pk):
        return self.http_client.post(reverse(f"{self.name}-refund", kwargs={"pk": pk}))

    def refund_product(self, pk, rel_id):
        return self.http_client.post(reverse(f"{self.name}-refund-product", kwargs={"pk": pk, "rel_id": rel_id}))

    def import_template(self, *, product_id: str | None = None):
        params = {"product_id": product_id} if product_id is not None else None
        return self.http_client.get(reverse(f"{self.name}-import-template"), params)

    def import_csv(self, *, csv_file=None):
        # multipart 업로드 — csv_file 부재 시 None 으로 전달해 view 의 missing-file 처리 분기 검증 가능.
        data = {"csv_file": csv_file} if csv_file is not None else {}
        return self.http_client.post(reverse(f"{self.name}-import-csv"), data, format="multipart")

    def export(self, params=None):
        url = reverse(f"{self.name}-export")
        if params:
            url = f"{url}?{urlencode(params, doseq=True)}"
        return self.http_client.post(url, format="json")


class OrderNotificationsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-order-notification"

    def preview(self, data=None):
        return self.http_client.post(reverse(f"{self.name}-preview"), data, format="json")

    def send(self, data=None):
        return self.http_client.post(reverse(f"{self.name}-send"), data, format="json")


class CategoryGroupsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-category-group"


class TagsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-tag"


class ProductsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-product"


class OptionGroupsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-option-group"


class IssuedDocumentsAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-document-issued"

    def revoke(self, pk):
        return self.http_client.post(reverse(f"{self.name}-revoke", kwargs={"pk": pk}))


class DocumentTemplatesAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-document-template"
