from unittest.mock import patch

import pytest
from core.const.shop_error_messages import PortOneWebhookFailureMessages
from core.external_apis.portone.client import PortOneException
from core.util.testutil import errors_payload
from rest_framework import serializers as drf_serializers
from shop.order.models import Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistoryStatus
from shop.payment_history.serializers import PortOneV1WebhookRequestSerializer, PortOneV1WebhookRequestStatus
from shop.test.helpers import make_portone_payment_info, make_webhook_payload


def test_validate_status_accepts_paid() -> None:
    # validate_status 단독 호출 — is_valid() 를 거치면 다른 필드 / DB 의 무관한 실패가 섞임.
    serializer = PortOneV1WebhookRequestSerializer()
    assert serializer.validate_status("paid") == "paid"


@pytest.mark.parametrize(
    ("status_value", "expected_error"),
    [
        (
            "ready",
            {"detail": PortOneWebhookFailureMessages.VIRTUAL_ACCOUNT_NOT_SUPPORTED, "code": "unsupported"},
        ),
        (
            "failed",
            {"detail": PortOneWebhookFailureMessages.PURCHASE_FAILED, "code": "forgery"},
        ),
        (
            "cancelled",
            {"detail": PortOneWebhookFailureMessages.CANCELLED_NOT_SUPPORTED, "code": "unsupported"},
        ),
    ],
)
def test_validate_status_rejects_non_paid(status_value: str, expected_error: dict) -> None:
    # merchant_uid 는 status 가 먼저 거절돼 도달하지 않는 dummy.
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid="y", status=status_value))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"status": [expected_error]}


@pytest.mark.django_db
def test_validate_rejects_when_merchant_uid_matches_no_order_or_cart(mock_portone_find_payment_info) -> None:
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid="00000000-0000-0000-0000-000000000000")
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureMessages.ORDER_NOT_FOUND, "code": "forgery"}],
    }
    # order 못 찾으면 PortOne API 호출 자체를 건너뛰는 게 invariant — validate 순서가 뒤바뀌어 PortOne 먼저 호출하는 회귀를 catch.
    mock_portone_find_payment_info.assert_not_called()


@pytest.mark.django_db
def test_validate_rejects_when_portone_api_returns_non_paid_status(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, status="ready")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureMessages.UNEXPECTED_RETRIEVED_ORDER_STATUS, "code": "forgery"}
        ],
    }


@pytest.mark.django_db
def test_validate_rejects_when_currency_is_not_krw(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, currency="USD")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureMessages.UNSUPPORTED_CURRENCY, "code": "forgery"}],
    }


@pytest.mark.django_db
def test_validate_rejects_when_retrieved_merchant_uid_does_not_match(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, merchant_uid="different-merchant-uid"
    )
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureMessages.UNEXPECTED_RETRIEVED_ORDER_ID, "code": "forgery"}
        ],
    }


@pytest.mark.django_db
def test_validate_rejects_when_paid_amount_does_not_match_order_price(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price - 1
    )
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureMessages.UNEXPECTED_PAID_PRICE, "code": "forgery"}],
    }


@pytest.mark.django_db
def test_validate_rejects_when_portone_api_raises(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.side_effect = PortOneException("PortOne 서버 통신 실패")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": "PortOne 서버 통신 실패", "code": "portone_error"}],
    }


@pytest.mark.django_db
def test_validate_passes_happy_path_for_order(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid()
    assert serializer.validated_data["status"] == PortOneV1WebhookRequestStatus.PAID


@pytest.mark.django_db
def test_validate_passes_happy_path_for_single_product_cart(single_product_cart, mock_portone_find_payment_info):
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=single_product_cart)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(single_product_cart.id)))
    assert serializer.is_valid()
    assert serializer.validated_data["status"] == PortOneV1WebhookRequestStatus.PAID


@pytest.mark.django_db
def test_create_completes_pending_order(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, imp_uid="imp_done")
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid=str(pending_order.id), imp_uid="imp_done")
    )
    assert serializer.is_valid()

    payment_history = serializer.create(serializer.validated_data)

    assert payment_history.status == PaymentHistoryStatus.completed
    assert payment_history.imp_id == "imp_done"
    assert payment_history.price == pending_order.first_paid_price
    statuses = list(pending_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.paid]


@pytest.mark.django_db
def test_create_promotes_single_product_cart_to_order(single_product_cart, mock_portone_find_payment_info):
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=single_product_cart)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(single_product_cart.id)))
    assert serializer.is_valid()

    serializer.create(serializer.validated_data)

    assert not SingleProductCart.objects.filter(id=single_product_cart.id).exists()
    promoted_order = Order.objects.get(id=single_product_cart.id)
    assert promoted_order.payment_histories.get().status == PaymentHistoryStatus.completed


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_status", ["completed", "refunded", "partial_refunded"])
def test_create_rejects_webhook_when_state_machine_blocks(
    terminal_status, order_factory, mock_portone_find_payment_info
):
    # 결제 완료 / 환불 / 부분환불 어느 terminal state 든 webhook 재시도 (pending → completed 외 전이) 는 거절.
    order = order_factory(status=terminal_status)
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(order.id)))
    assert serializer.is_valid()

    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer.create(serializer.validated_data)
    assert errors_payload(exc_info.value.detail) == [
        {"detail": PortOneWebhookFailureMessages.ILLEGAL_STATUS_TRANSITION, "code": "illegal_transition"},
    ]


@pytest.mark.django_db
def test_create_registers_notification_task_on_commit(mock_portone_find_payment_info, mocked_on_commit, order_factory):
    pending_order = order_factory()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    assert serializer.is_valid()

    serializer.create(serializer.validated_data)

    assert mocked_on_commit.call_count == 1
    callback = mocked_on_commit.call_args.args[0]
    with patch("shop.payment_history.serializers.send_payment_completed_notifications.delay") as mock_delay:
        callback()
    mock_delay.assert_called_once_with(str(pending_order.id))


@pytest.mark.django_db
def test_strict_mock_raises_when_return_value_not_set(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory()
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(pending_order.id)))
    with pytest.raises(RuntimeError, match="without an explicit `.return_value`"):
        serializer.is_valid()


@pytest.mark.django_db
def test_create_rolls_back_when_state_machine_blocks(mock_portone_find_payment_info, order_factory):
    completed_order = order_factory(status="completed")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=completed_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=str(completed_order.id)))
    assert serializer.is_valid()

    with pytest.raises(drf_serializers.ValidationError):
        serializer.create(serializer.validated_data)

    # completed_order fixture 의 알려진 초기 상태 — PH 1개 (completed), OPR 1개 (paid) — 가 유지돼야 함.
    completed_order.refresh_from_db()
    assert completed_order.payment_histories.count() == 1
    assert list(completed_order.products.values_list("status", flat=True)) == [
        OrderProductRelation.OrderProductStatus.paid,
    ]
