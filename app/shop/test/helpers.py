from core.util.totp import TOTPInfo
from django.conf import settings


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
        "merchant_uid": str(order.id),
        "amount": order.first_paid_price,
        "cancel_amount": 0,
        "currency": "KRW",
        "status": "paid",
    } | overrides
