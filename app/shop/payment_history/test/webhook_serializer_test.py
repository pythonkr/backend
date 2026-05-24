import uuid
from unittest.mock import patch

import pytest
from core.const.shop_error_messages import PortOneWebhookFailureCode
from core.external_apis.portone.client import PortOneException
from core.util.testutil import errors_payload
from rest_framework import serializers as drf_serializers
from shop.order.models import Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistoryStatus, PaymentWebhookEvent
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
            {
                "detail": PortOneWebhookFailureCode.VIRTUAL_ACCOUNT_NOT_SUPPORTED.label,
                "code": "VIRTUAL_ACCOUNT_NOT_SUPPORTED",
            },
        ),
        (
            "failed",
            {"detail": PortOneWebhookFailureCode.PURCHASE_FAILED.label, "code": "PURCHASE_FAILED"},
        ),
        (
            "cancelled",
            {"detail": PortOneWebhookFailureCode.CANCELLED_NOT_SUPPORTED.label, "code": "CANCELLED_NOT_SUPPORTED"},
        ),
    ],
)
@pytest.mark.django_db
def test_validate_status_rejects_non_paid(status_value: str, expected_error: dict) -> None:
    # merchant_uid 는 status 가 먼저 거절돼 도달하지 않는 dummy.
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid="y", status=status_value))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {"status": [expected_error]}
    assert PaymentWebhookEvent.objects.filter(
        event_type=PaymentWebhookEvent.EventType.PAYMENT_REJECTED,
        reason_code=expected_error["code"],
    ).exists()


@pytest.mark.django_db
def test_validate_rejects_when_merchant_uid_matches_no_order_or_cart(mock_portone_find_payment_info) -> None:
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid="00000000-0000-0000-0000-000000000000")
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureCode.ORDER_NOT_FOUND.label, "code": "ORDER_NOT_FOUND"}],
    }
    # order 못 찾으면 PortOne API 호출 자체를 건너뛰는 게 invariant — validate 순서가 뒤바뀌어 PortOne 먼저 호출하는 회귀를 catch.
    mock_portone_find_payment_info.assert_not_called()
    assert PaymentWebhookEvent.objects.filter(
        event_type=PaymentWebhookEvent.EventType.PAYMENT_REJECTED,
        reason_code="ORDER_NOT_FOUND",
    ).exists()


@pytest.mark.django_db
def test_non_string_merchant_uid_is_rejected_before_portone_lookup(mock_portone_find_payment_info) -> None:
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=1234))

    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureCode.ORDER_NOT_FOUND.label, "code": "ORDER_NOT_FOUND"}],
    }
    mock_portone_find_payment_info.assert_not_called()


@pytest.mark.django_db
def test_validate_rejects_when_parsed_merchant_uid_matches_no_order_or_cart(mock_portone_find_payment_info) -> None:
    unknown_order = Order(id=uuid.uuid4(), prepared_cart_hash="a" * 16)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=unknown_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": PortOneWebhookFailureCode.ORDER_NOT_FOUND.label, "code": "ORDER_NOT_FOUND"}],
    }
    mock_portone_find_payment_info.assert_not_called()


@pytest.mark.django_db
def test_validate_rejects_when_portone_api_returns_non_paid_status(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, status="ready")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": PortOneWebhookFailureCode.UNEXPECTED_RETRIEVED_ORDER_STATUS.label,
                "code": "UNEXPECTED_RETRIEVED_ORDER_STATUS",
            }
        ],
    }


@pytest.mark.django_db
def test_validate_rejects_when_currency_is_not_krw(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, currency="USD")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureCode.UNSUPPORTED_CURRENCY.label, "code": "UNSUPPORTED_CURRENCY"}
        ],
    }
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=pending_order.first_paid_price,
        current_leftover_price=pending_order.first_paid_price,
        reason=PortOneWebhookFailureCode.UNSUPPORTED_CURRENCY.label,
    )


@pytest.mark.django_db
def test_validate_rejects_when_retrieved_merchant_uid_does_not_match(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, merchant_uid="different-merchant-uid"
    )
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {
                "detail": PortOneWebhookFailureCode.UNEXPECTED_RETRIEVED_ORDER_ID.label,
                "code": "UNEXPECTED_RETRIEVED_ORDER_ID",
            }
        ],
    }


@pytest.mark.django_db
def test_validate_rejects_when_paid_amount_does_not_match_order_price(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price - 1
    )
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label, "code": "UNEXPECTED_PAID_PRICE"}
        ],
    }
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=pending_order.first_paid_price - 1,
        current_leftover_price=pending_order.first_paid_price - 1,
        reason=PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label,
    )


@pytest.mark.django_db
def test_validate_rejects_fractional_paid_amount(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price + 0.5
    )
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))

    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label, "code": "UNEXPECTED_PAID_PRICE"}
        ],
    }
    leftover_price = pending_order.first_paid_price + 0.5
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=leftover_price,
        current_leftover_price=leftover_price,
        reason=PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label,
    )


@pytest.mark.django_db
def test_validate_reports_cancel_failure_on_invalid_paid_payment(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price + 1
    )
    mock_portone_req_cancel_payment.side_effect = PortOneException("PortOne 취소 실패")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))

    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": "PortOne 취소 실패", "code": "portone_cancel_error"}],
    }
    event = PaymentWebhookEvent.objects.get(event_type=PaymentWebhookEvent.EventType.CANCEL_FAILED)
    assert event.reason_code == "PortOneException"
    assert "Traceback (most recent call last)" in event.reason
    assert "PortOne 취소 실패" in event.reason


@pytest.mark.django_db
def test_validate_records_cancel_succeeded_event_on_invalid_paid_payment(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(
        order=pending_order, amount=pending_order.first_paid_price + 1
    )
    cancel_response = {
        "imp_uid": "imp_test",
        "status": "cancelled",
        "cancel_amount": pending_order.first_paid_price + 1,
    }
    mock_portone_req_cancel_payment.return_value = cancel_response
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))

    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label, "code": "UNEXPECTED_PAID_PRICE"}
        ],
    }
    event = PaymentWebhookEvent.objects.get(event_type=PaymentWebhookEvent.EventType.CANCEL_SUCCEEDED)
    assert event.cancel_response == cancel_response
    assert event.reason_code == "UNEXPECTED_PAID_PRICE"


@pytest.mark.django_db
def test_validate_rejects_when_portone_api_raises(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.side_effect = PortOneException("PortOne 서버 통신 실패")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": "PortOne 서버 통신 실패", "code": "portone_error"}],
    }
    event = PaymentWebhookEvent.objects.get(event_type=PaymentWebhookEvent.EventType.PAYMENT_LOOKUP_FAILED)
    assert event.reason_code == "PortOneException"
    assert "Traceback (most recent call last)" in event.reason
    assert "PortOne 서버 통신 실패" in event.reason


@pytest.mark.django_db
def test_validate_passes_happy_path_for_order(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid()
    assert serializer.validated_data["status"] == PortOneV1WebhookRequestStatus.PAID


@pytest.mark.django_db
def test_validate_passes_happy_path_for_single_product_cart(single_product_cart, mock_portone_find_payment_info):
    single_product_cart.prepare_payment()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=single_product_cart)
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid=single_product_cart.merchant_uid)
    )
    assert serializer.is_valid()
    assert serializer.validated_data["status"] == PortOneV1WebhookRequestStatus.PAID


@pytest.mark.django_db
def test_create_completes_pending_order(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order, imp_uid="imp_done")
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid=pending_order.merchant_uid, imp_uid="imp_done")
    )
    assert serializer.is_valid()

    payment_history = serializer.save()

    assert payment_history.status == PaymentHistoryStatus.completed
    assert payment_history.imp_id == "imp_done"
    assert payment_history.price == pending_order.first_paid_price
    statuses = list(pending_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.paid]


@pytest.mark.django_db
def test_create_promotes_single_product_cart_to_order(single_product_cart, mock_portone_find_payment_info):
    single_product_cart.prepare_payment()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=single_product_cart)
    serializer = PortOneV1WebhookRequestSerializer(
        data=make_webhook_payload(merchant_uid=single_product_cart.merchant_uid)
    )
    assert serializer.is_valid()

    serializer.save()

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
    order.prepare_payment()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=order.merchant_uid))
    assert serializer.is_valid()

    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer.save()
    assert errors_payload(exc_info.value.detail) == [
        {"detail": PortOneWebhookFailureCode.ILLEGAL_STATUS_TRANSITION.label, "code": "ILLEGAL_STATUS_TRANSITION"},
    ]


@pytest.mark.django_db
def test_create_registers_notification_task_on_commit(mock_portone_find_payment_info, mocked_on_commit, order_factory):
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid()

    serializer.save()

    assert mocked_on_commit.call_count == 1
    callback = mocked_on_commit.call_args.args[0]
    with patch("shop.payment_history.serializers.send_payment_completed_notifications.delay") as mock_delay:
        callback()
    mock_delay.assert_called_once_with(str(pending_order.id))


@pytest.mark.django_db
def test_strict_mock_raises_when_return_value_not_set(mock_portone_find_payment_info, order_factory):
    pending_order = order_factory(status="prepared")
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    with pytest.raises(RuntimeError, match="without an explicit `.return_value`"):
        serializer.is_valid()


@pytest.mark.django_db
def test_reject_and_cancel_paid_payment_skips_cancel_when_leftover_is_zero():
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid="merchant"))
    payment_info = {
        "imp_uid": "imp_zero",
        "merchant_uid": "merchant",
        "amount": 1000,
        "cancel_amount": 1000,
        "currency": "KRW",
        "status": "paid",
    }

    # cached_property 자리에 직접 주입 — portone_payment_info access 시 DB/HTTP 호출 없이 이 값을 사용.
    serializer.__dict__["portone_payment_info"] = payment_info
    with pytest.raises(drf_serializers.ValidationError):
        serializer._reject_and_cancel_paid_payment(PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE)


@pytest.mark.django_db
def test_validate_rejects_invalid_merchant_uid_before_portone_lookup(mock_portone_find_payment_info):
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid="invalid"))

    assert serializer.is_valid() is False
    mock_portone_find_payment_info.assert_not_called()


@pytest.mark.django_db
def test_create_rejects_and_cancels_when_snapshot_invalidated_between_validate_and_create(
    mock_portone_find_payment_info, mock_portone_req_cancel_payment, order_factory
):
    # validate() 통과 후 create() 진입 전에 다른 트랜잭션이 cart 의 prepared snapshot 을 무효화하는 race 시뮬레이션.
    # 실제 코드 경로에선 OPR.save 가 hash 까지 바꾸지만, 그 경우 _lock_or_promote_order 가 먼저 ORDER_NOT_FOUND 로 거절됨.
    # 여기선 create() 의 방어 분기 (matches_payment_preparation 재검사) 만 격리 cover.
    pending_order = order_factory(status="prepared")
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=pending_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=pending_order.merchant_uid))
    assert serializer.is_valid()

    with patch.object(Order, "matches_payment_preparation", return_value=False):
        with pytest.raises(drf_serializers.ValidationError) as exc_info:
            serializer.save()

    assert errors_payload(exc_info.value.detail) == [
        {"detail": PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label, "code": "UNEXPECTED_PAID_PRICE"},
    ]
    mock_portone_req_cancel_payment.assert_called_once_with(
        imp_id="imp_test",
        refund_request_price=pending_order.first_paid_price,
        current_leftover_price=pending_order.first_paid_price,
        reason=PortOneWebhookFailureCode.UNEXPECTED_PAID_PRICE.label,
    )


@pytest.mark.django_db
def test_create_rolls_back_when_state_machine_blocks(mock_portone_find_payment_info, order_factory):
    completed_order = order_factory(status="completed")
    completed_order.prepare_payment()
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=completed_order)
    serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=completed_order.merchant_uid))
    assert serializer.is_valid()

    with pytest.raises(drf_serializers.ValidationError):
        serializer.save()

    # completed_order fixture 의 알려진 초기 상태 — PH 1개 (completed), OPR 1개 (paid) — 가 유지돼야 함.
    completed_order.refresh_from_db()
    assert completed_order.payment_histories.count() == 1
    assert list(completed_order.products.values_list("status", flat=True)) == [
        OrderProductRelation.OrderProductStatus.paid,
    ]
