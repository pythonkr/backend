import pytest
from core.const.shop_error_messages import PortOneWebhookFailureCode
from core.external_apis.portone.client import PortOneException
from django.test import override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from rest_framework.test import APIClient
from shop.conftest import WEBHOOK_WHITELISTED_IP
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus, PaymentWebhookEvent
from shop.test.helpers import make_portone_payment_info, make_webhook_payload

_NON_WHITELISTED_IP = "5.6.7.8"


def _post_webhook(
    *,
    merchant_uid: str,
    ip: str | None = None,
    xff: str | None = None,
    x_real_ip: str | None = None,
    status: str = "paid",
    imp_uid: str = "imp_x",
) -> Response:
    meta: dict[str, str] = {}
    if ip is not None:
        meta["REMOTE_ADDR"] = ip
    if xff is not None:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    if x_real_ip is not None:
        meta["HTTP_X_REAL_IP"] = x_real_ip
    return APIClient().post(
        path=reverse("v1:payment_histories-list"),
        data=make_webhook_payload(merchant_uid=merchant_uid, status=status, imp_uid=imp_uid),
        format="json",
        **meta,
    )


@pytest.mark.parametrize(
    ("debug", "expected_status", "expected_body"),
    [
        (
            False,
            HTTP_403_FORBIDDEN,
            {
                "type": "client_error",
                "errors": [{"code": "permission_denied", "detail": "이 작업을 수행할 권한이 없습니다.", "attr": None}],
            },
        ),
        (
            True,
            HTTP_200_OK,
            {"status": "success", "message": "일반 결제 성공"},
        ),
    ],
)
@pytest.mark.django_db
def test_ip_allowlist_respects_debug_bypass(
    debug, expected_status, expected_body, mock_portone_find_payment_info, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    with override_settings(DEBUG=debug):
        response = _post_webhook(merchant_uid=pending_order.merchant_uid, ip=_NON_WHITELISTED_IP)

    assert response.status_code == expected_status
    assert response.json() == expected_body

    if expected_status == HTTP_200_OK:
        assert PaymentHistory.objects.filter(
            order=pending_order,
            imp_id="imp_x",
            status=PaymentHistoryStatus.completed,
            price=pending_order.first_paid_price,
        ).exists()
    else:
        # 403 은 view 진입을 막아 serializer 가 호출 자체가 안 되므로 strict filter 가 아닌 "PH 가 아예 없음" 으로 단언.
        assert not PaymentHistory.objects.filter(order=pending_order).exists()


@pytest.mark.parametrize(
    "post_kwargs",
    [
        # 테스트 환경에서 REMOTE_ADDR 만 직접 지정 (프록시 없음).
        {"ip": WEBHOOK_WHITELISTED_IP},
        # nginx 뒤 운영: REMOTE_ADDR 은 nginx 컨테이너 IP, 실제 IP 는 X-Forwarded-For 만.
        {"ip": _NON_WHITELISTED_IP, "xff": WEBHOOK_WHITELISTED_IP},
        # 프록시가 X-Real-IP 만 채우는 변형.
        {"ip": _NON_WHITELISTED_IP, "x_real_ip": WEBHOOK_WHITELISTED_IP},
        # nginx 가 두 헤더 모두 채우는 일반적인 구성.
        {"ip": _NON_WHITELISTED_IP, "xff": WEBHOOK_WHITELISTED_IP, "x_real_ip": WEBHOOK_WHITELISTED_IP},
        # 다중 hop X-Forwarded-For — leftmost(원 클라이언트) 가 화이트리스트면 통과.
        {"ip": _NON_WHITELISTED_IP, "xff": f"{WEBHOOK_WHITELISTED_IP}, 10.0.0.1, 10.0.0.2"},
    ],
)
@pytest.mark.django_db
def test_accepts_request_from_whitelisted_ip(post_kwargs, mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    response = _post_webhook(merchant_uid=pending_order.merchant_uid, **post_kwargs)
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"status": "success", "message": "일반 결제 성공"}
    assert PaymentHistory.objects.filter(
        order=pending_order,
        imp_id="imp_x",
        status=PaymentHistoryStatus.completed,
        price=pending_order.first_paid_price,
    ).exists()


@pytest.mark.django_db
def test_atomic_rollback_on_validation_failure(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price + 9999
    )
    response = _post_webhook(merchant_uid=pending_order.merchant_uid, ip=WEBHOOK_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        "errors": [
            {
                "code": "UNEXPECTED_PAID_PRICE",
                "detail": PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label,
                "attr": "non_field_errors",
            }
        ],
    }
    assert not PaymentHistory.objects.filter(order=pending_order).exists()
    leftover_price = pending_order.first_paid_price + 9999
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=leftover_price,
        current_leftover_price=leftover_price,
        reason=PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label,
    )


@pytest.mark.parametrize(
    ("status_value", "expected_error"),
    [
        (
            "failed",
            {"code": "PURCHASE_FAILED", "detail": PortOneWebhookFailureCode.PURCHASE_FAILED.label, "attr": "status"},
        ),
        (
            "ready",
            {
                "code": "VIRTUAL_ACCOUNT_NOT_SUPPORTED",
                "detail": PortOneWebhookFailureCode.VIRTUAL_ACCOUNT_NOT_SUPPORTED.label,
                "attr": "status",
            },
        ),
        (
            "cancelled",
            {
                "code": "CANCELLED_NOT_SUPPORTED",
                "detail": PortOneWebhookFailureCode.CANCELLED_NOT_SUPPORTED.label,
                "attr": "status",
            },
        ),
    ],
)
@pytest.mark.django_db
def test_rejects_non_paid_status_with_standardized_error(
    status_value, expected_error, mock_portone_find_payment_info, order_factory
):
    pending_order = order_factory(status="prepared")
    response = _post_webhook(merchant_uid=pending_order.merchant_uid, ip=WEBHOOK_WHITELISTED_IP, status=status_value)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {"type": "validation_error", "errors": [expected_error]}
    mock_portone_find_payment_info.assert_not_called()
    assert not PaymentHistory.objects.filter(order=pending_order).exists()
    assert PaymentWebhookEvent.objects.filter(
        event_type=PaymentWebhookEvent.EventType.PAYMENT_REJECTED,
        reason_code=expected_error["code"],
    ).exists()


@pytest.mark.django_db
def test_rejects_unknown_merchant_uid(mock_portone_find_payment_info):
    # 해당 PK 의 Order/Cart 둘 다 없음 → ORDER_NOT_FOUND. PortOne 호출 안 일어남.
    response = _post_webhook(merchant_uid="00000000-0000-0000-0000-000000000000", ip=WEBHOOK_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        "errors": [
            {
                "code": "ORDER_NOT_FOUND",
                "detail": PortOneWebhookFailureCode.ORDER_NOT_FOUND.label,
                "attr": "non_field_errors",
            }
        ],
    }
    mock_portone_find_payment_info.assert_not_called()
    assert PaymentWebhookEvent.objects.filter(
        event_type=PaymentWebhookEvent.EventType.PAYMENT_REJECTED,
        reason_code="ORDER_NOT_FOUND",
    ).exists()


@pytest.mark.django_db
def test_rejects_missing_required_fields():
    # `merchant_uid` / `imp_uid` 누락 — field-level required error 반환.
    response = APIClient().post(
        path=reverse("v1:payment_histories-list"),
        data={"status": "paid"},
        format="json",
        REMOTE_ADDR=WEBHOOK_WHITELISTED_IP,
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["type"] == "validation_error"
    assert {(e["attr"], e["code"]) for e in body["errors"]} == {("imp_uid", "required"), ("merchant_uid", "required")}


@pytest.mark.django_db
def test_rejects_when_currency_is_not_krw(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, currency="USD")
    response = _post_webhook(merchant_uid=pending_order.merchant_uid, ip=WEBHOOK_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        "errors": [
            {
                "code": "UNSUPPORTED_CURRENCY",
                "detail": PortOneWebhookFailureCode.UNSUPPORTED_CURRENCY.label,
                "attr": "non_field_errors",
            }
        ],
    }
    assert not PaymentHistory.objects.filter(order=pending_order).exists()
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=pending_order.first_paid_price,
        current_leftover_price=pending_order.first_paid_price,
        reason=PortOneWebhookFailureCode.UNSUPPORTED_CURRENCY.label,
    )


@pytest.mark.django_db
def test_rejects_duplicate_webhook_on_already_completed_order(mock_portone_find_payment_info, order_factory):
    completed_order = order_factory(status="completed")
    completed_order.prepare_payment()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=completed_order, imp_uid="imp_x")
    response = _post_webhook(merchant_uid=completed_order.merchant_uid, ip=WEBHOOK_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        # `create()` 안에서 직접 raise 되므로 drf_standardized_errors 가 `attr=None` 으로 매핑.
        "errors": [
            {
                "code": "ILLEGAL_STATUS_TRANSITION",
                "detail": PortOneWebhookFailureCode.ILLEGAL_STATUS_TRANSITION.label,
                "attr": None,
            }
        ],
    }
    # PaymentHistory 는 fixture 가 만든 1건만 유지.
    assert PaymentHistory.objects.filter(order=completed_order).count() == 1
    assert PaymentWebhookEvent.objects.filter(
        event_type=PaymentWebhookEvent.EventType.PAYMENT_REJECTED,
        order=completed_order,
        reason_code="ILLEGAL_STATUS_TRANSITION",
    ).exists()


@pytest.mark.django_db
def test_rejects_when_portone_api_raises(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.side_effect = PortOneException("PortOne 서버 통신 실패")
    response = _post_webhook(merchant_uid=pending_order.merchant_uid, ip=WEBHOOK_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["type"] == "validation_error"
    assert body["errors"][0]["code"] == "portone_error"
    assert not PaymentHistory.objects.filter(order=pending_order).exists()
