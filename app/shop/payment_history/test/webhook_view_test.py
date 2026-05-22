from types import SimpleNamespace

import pytest
from core.const.shop_error_messages import PortOneWebhookFailureMessages as Msgs
from django.test import override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from rest_framework.test import APIClient
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.test.helpers import make_portone_payment_info, make_webhook_payload

_WHITELISTED_IP = "1.2.3.4"
_NON_WHITELISTED_IP = "5.6.7.8"


@pytest.fixture(autouse=True)
def _default_webhook_settings():
    with override_settings(
        DEBUG=False,
        PORTONE=SimpleNamespace(
            api_url="https://api.example-portone.kr",
            ip_list=[_WHITELISTED_IP],
            imp_key="portone_api_key",
            imp_secret="portone_api_secret",  # nosec: B106
        ),
    ):
        yield


def _post_webhook(*, merchant_uid: str, ip: str) -> Response:
    return APIClient().post(
        path=reverse("v1:payment_histories-list"),
        data=make_webhook_payload(merchant_uid=merchant_uid),
        format="json",
        REMOTE_ADDR=ip,
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
    debug, expected_status, expected_body, pending_order, mock_portone_find_payment_info
):
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    with override_settings(DEBUG=debug):
        response = _post_webhook(merchant_uid=str(pending_order.id), ip=_NON_WHITELISTED_IP)

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


@pytest.mark.django_db
def test_accepts_request_from_whitelisted_ip(pending_order, mock_portone_find_payment_info):
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    response = _post_webhook(merchant_uid=str(pending_order.id), ip=_WHITELISTED_IP)
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"status": "success", "message": "일반 결제 성공"}
    assert PaymentHistory.objects.filter(
        order=pending_order,
        imp_id="imp_x",
        status=PaymentHistoryStatus.completed,
        price=pending_order.first_paid_price,
    ).exists()


@pytest.mark.django_db
def test_atomic_rollback_on_validation_failure(pending_order, mock_portone_find_payment_info):
    # 금액 변조 → validate 실패. PaymentHistory 가 절대 생기면 안 됨.
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price + 9999
    )
    response = _post_webhook(merchant_uid=str(pending_order.id), ip=_WHITELISTED_IP)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {
        "type": "validation_error",
        "errors": [{"code": "forgery", "detail": Msgs.UNEXPECTED_PAID_PRICE, "attr": "non_field_errors"}],
    }
    assert not PaymentHistory.objects.filter(order=pending_order).exists()
