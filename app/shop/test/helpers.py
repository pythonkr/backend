from types import SimpleNamespace
from typing import ClassVar

from core.util.testutil import ModelApiFixture
from core.util.totp import TOTPInfo
from django.conf import settings
from django.urls import reverse


class OrdersApi(ModelApiFixture):
    name: ClassVar[str] = "v1:orders"

    def create_single(self, data=None):
        return self.http_client.post(reverse(f"{self.name}-create-single-product-order"), data, format="json")

    def retrieve_receipt(self, pk):
        return self.http_client.get(reverse(f"{self.name}-retrieve-receipt", args=(pk,)))


class OrderProductsApi(ModelApiFixture):
    name: ClassVar[str] = "v1:order-products"

    def modify_options(self, order_id, opr_id, data=None):
        return self.http_client.patch(
            reverse(f"{self.name}-modify-options", kwargs={"order_id": order_id, "order_product_rel_id": opr_id}),
            data,
            format="json",
        )

    def delete_partial(self, order_id, opr_id):
        return self.http_client.delete(
            reverse(f"{self.name}-detail", kwargs={"order_id": order_id, "order_product_rel_id": opr_id})
        )


class CartApi(ModelApiFixture):
    name: ClassVar[str] = "v1:cart"


class CartProductsApi(ModelApiFixture):
    name: ClassVar[str] = "v1:cart-products"


class ScanCodeApi(ModelApiFixture):
    name: ClassVar[str] = "v1:scancode"


class ProductsApi(ModelApiFixture):
    name: ClassVar[str] = "v1:products"


class PatronApi(ModelApiFixture):
    name: ClassVar[str] = "v1:patron"


class OrdersAdminApi(ModelApiFixture):
    name: ClassVar[str] = "v1:admin-shop-order"

    def refund(self, pk, *, totp: str | None = None):
        url = reverse(f"{self.name}-refund", kwargs={"pk": pk})
        if totp is not None:
            url += f"?totp={totp}"
        return self.http_client.post(url)

    def refund_product(self, pk, rel_id, *, totp: str | None = None):
        url = reverse(f"{self.name}-refund-product", kwargs={"pk": pk, "rel_id": rel_id})
        if totp is not None:
            url += f"?totp={totp}"
        return self.http_client.post(url)

    def import_template(self, *, product_id: str | None = None):
        params = {"product_id": product_id} if product_id is not None else None
        return self.http_client.get(reverse(f"{self.name}-import-template"), params)

    def import_csv(self, *, csv_file=None):
        # multipart 업로드 — csv_file 부재 시 None 으로 전달해 view 의 missing-file 처리 분기 검증 가능.
        data = {"csv_file": csv_file} if csv_file is not None else {}
        return self.http_client.post(reverse(f"{self.name}-import-csv"), data, format="multipart")

    def export(self, data=None):
        return self.http_client.post(reverse(f"{self.name}-export"), data, format="json")


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


class PortOneWebhookApi(ModelApiFixture):
    name: ClassVar[str] = "v1:payment_histories"

    def notify(self, *, merchant_uid: str, ip: str, status: str = "paid", imp_uid: str = "imp_x"):
        # PortOne 서버 IP 검증을 위해 REMOTE_ADDR 명시 — IP allowlist 통과 / 거절 테스트 양쪽 지원.
        return self.http_client.post(
            reverse(f"{self.name}-list"),
            data=make_webhook_payload(merchant_uid=merchant_uid, status=status, imp_uid=imp_uid),
            format="json",
            REMOTE_ADDR=ip,
        )


def make_serializer_context(user, **extras) -> dict:
    """serializer context 헬퍼 — `{"request": SimpleNamespace(user=user), **extras}` 반환.

    cart_validation serializer 들이 `self.context["request"].user` 만 참조하므로 실 DRF Request 객체 불필요.
    `mode` 등 추가 키는 kwargs 로 합쳐짐.
    """
    return {"request": SimpleNamespace(user=user), **extras}


def valid_refund_totp() -> str:
    """현재 시각 기준 유효한 환불 승인 TOTP — settings.SHOP.refund_authorizer_secret_key 와 동기화."""
    return TOTPInfo(key=settings.SHOP.refund_authorizer_secret_key.encode()).get_totp()[0]


def make_webhook_payload(*, merchant_uid: str, status: str = "paid", imp_uid: str = "imp_x") -> dict:
    """PortOne 이 우리 webhook 으로 보내는 request body — `PortOneV1WebhookRequestSerializer` 의 입력."""
    return {"status": status, "imp_uid": imp_uid, "merchant_uid": merchant_uid}


def make_portone_payment_info(*, order, **overrides) -> dict:
    """PortOne `find_payment_info` 응답 — order/cart 의 id 와 first_paid_price 를 default 로 추출.

    검증 통과 default 응답을 만들고, 특정 필드만 흔드는 테스트는 kwargs override
    (e.g. `status="ready"`, `currency="USD"`, `amount=order.first_paid_price - 1`).
    `order` 는 duck-typed — `id` + `first_paid_price` 를 가진 Order / SingleProductCart 둘 다 받음.
    """
    return {
        "imp_uid": "imp_test",
        "merchant_uid": order.merchant_uid,
        "amount": order.first_paid_price,
        "cancel_amount": 0,
        "currency": "KRW",
        "status": "paid",
    } | overrides
