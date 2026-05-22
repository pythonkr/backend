from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import NotRefundableErrorMessages, PermissionErrorMessages
from core.external_apis.portone.client import PortOneException
from core.util.testutil import errors_payload
from freezegun import freeze_time
from shop.order.models import OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.serializers.refund import OrderProductRefundSerializer, OrderTotalRefundSerializer
from shop.test.helpers import valid_refund_totp


@pytest.mark.django_db
def test_total_refund_happy_path_marks_all_oprs_refunded_and_records_payment_history(
    completed_order, mock_portone_req_cancel_payment
):
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid()

    serializer.refund()

    mock_portone_req_cancel_payment.assert_called_once_with(
        merchant_id=str(completed_order.id),
        refund_request_price=completed_order.first_paid_price,
        current_leftover_price=completed_order.first_paid_price,
    )
    statuses = list(completed_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.refunded]
    assert PaymentHistory.objects.filter(
        order=completed_order,
        imp_id=completed_order.latest_imp_id,
        status=PaymentHistoryStatus.refunded,
        price=0,
    ).exists()


@pytest.mark.django_db
def test_total_refund_rejects_when_order_has_no_imp_id(pending_order, mock_portone_req_cancel_payment):
    # CSV import 로 생성된 주문 (imp_id 없음) → PortOne 취소 불가능.
    serializer = OrderTotalRefundSerializer(
        instance=pending_order,
        data={"id": str(pending_order.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": NotRefundableErrorMessages.ORDER_IMP_ID_NOT_EXIST, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_total_refund_rejects_when_order_already_refunded(refunded_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(
        instance=refunded_order,
        data={"id": str(refunded_order.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_total_refund_rejects_when_any_opr_is_used(completed_order, mock_portone_req_cancel_payment):
    completed_order.products.update(status=OrderProductRelation.OrderProductStatus.used)
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_USED_TRY_AFTER_CHANGING_STATUS, "code": "invalid"},
        ],
    }
    mock_portone_req_cancel_payment.assert_not_called()


# _FAR_FUTURE (2099-12-31) 이후로 시간 이동 — product.refundable_ends_at 가 지남.
@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_total_refund_rejects_when_refund_window_expired(completed_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(
        instance=completed_order, data={"id": str(completed_order.id)}, context={"check_totp": False}
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [
            {"detail": NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED, "code": "invalid"},
        ],
    }
    mock_portone_req_cancel_payment.assert_not_called()


# check_refundable_date=False escape hatch — 운영자가 강제 환불 시 사용.
@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_total_refund_allows_expired_window_when_check_disabled(completed_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id)},
        context={"check_totp": False, "check_refundable_date": False},
    )
    assert serializer.is_valid()
    serializer.refund()
    mock_portone_req_cancel_payment.assert_called_once()


@pytest.mark.django_db
def test_total_refund_rolls_back_when_portone_cancel_fails(completed_order, mock_portone_req_cancel_payment):
    mock_portone_req_cancel_payment.side_effect = PortOneException("PortOne 취소 실패")
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid()

    with pytest.raises(PortOneException):
        serializer.refund()

    completed_order.refresh_from_db()
    assert list(completed_order.products.values_list("status", flat=True)) == [
        OrderProductRelation.OrderProductStatus.paid,
    ]
    # PaymentHistory 는 fixture 의 completed PH 1건만 남아있어야 함 (refunded PH 추가 안 됨).
    assert completed_order.payment_histories.count() == 1


@pytest.mark.django_db
def test_total_refund_rejects_when_totp_missing(completed_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(instance=completed_order, data={"id": str(completed_order.id)})
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "totp": [{"detail": PermissionErrorMessages.OTP_REQUIRED, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_total_refund_rejects_when_totp_invalid(completed_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id), "totp": "000000"},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "totp": [{"detail": PermissionErrorMessages.INVALID_OTP_CODE, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_total_refund_passes_with_valid_totp(completed_order, mock_portone_req_cancel_payment):
    serializer = OrderTotalRefundSerializer(
        instance=completed_order,
        data={"id": str(completed_order.id), "totp": valid_refund_totp()},
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_partial_refund_with_remaining_paid_creates_partial_refunded_history(
    completed_order, mock_portone_req_cancel_payment
):
    # 2번째 OPR 추가 후, 첫 OPR 만 환불 → 남은 paid OPR 1개 → partial_refunded.
    target_opr = completed_order.products.first()
    second_opr = OrderProductRelation.objects.create(
        order=completed_order,
        product=target_opr.product,
        price=target_opr.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    serializer = OrderProductRefundSerializer(
        instance=target_opr,
        data={"id": str(target_opr.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid()

    serializer.refund()

    target_opr.refresh_from_db()
    second_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    assert second_opr.status == OrderProductRelation.OrderProductStatus.paid
    assert PaymentHistory.objects.filter(order=completed_order, status=PaymentHistoryStatus.partial_refunded).exists()


@pytest.mark.django_db
def test_partial_refund_of_last_paid_opr_creates_full_refunded_history(
    completed_order, mock_portone_req_cancel_payment
):
    # OPR 1개 (completed_order fixture default) 를 환불 → 남은 paid 없음 → refunded.
    target_opr = completed_order.products.first()
    serializer = OrderProductRefundSerializer(
        instance=target_opr,
        data={"id": str(target_opr.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid()

    serializer.refund()

    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    assert PaymentHistory.objects.filter(order=completed_order, status=PaymentHistoryStatus.refunded).exists()


@pytest.mark.django_db
def test_partial_refund_calls_portone_with_correct_prices(completed_order, mock_portone_req_cancel_payment):
    target_opr = completed_order.products.first()
    # refund() 전 leftover 를 snapshot — `first_paid_price` 는 cached_property 라 호출 시점 의존성 회피.
    expected_leftover = completed_order.first_paid_price
    serializer = OrderProductRefundSerializer(
        instance=target_opr,
        data={"id": str(target_opr.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid()

    serializer.refund()

    mock_portone_req_cancel_payment.assert_called_once_with(
        merchant_id=str(completed_order.id),
        refund_request_price=target_opr.price + target_opr.donation_price,
        current_leftover_price=expected_leftover,
    )


@pytest.mark.parametrize(
    "non_paid_status",
    [OrderProductRelation.OrderProductStatus.refunded, OrderProductRelation.OrderProductStatus.used],
)
@pytest.mark.django_db
def test_partial_refund_rejects_when_opr_status_is_not_paid(
    completed_order, mock_portone_req_cancel_payment, non_paid_status
):
    target_opr = completed_order.products.first()
    target_opr.status = non_paid_status
    target_opr.save()

    serializer = OrderProductRefundSerializer(
        instance=target_opr,
        data={"id": str(target_opr.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": NotRefundableErrorMessages.PRODUCT_STATUS_IS_NOT_PAID, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()


@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_partial_refund_rejects_when_refund_window_expired(completed_order, mock_portone_req_cancel_payment):
    target_opr = completed_order.products.first()
    serializer = OrderProductRefundSerializer(
        instance=target_opr,
        data={"id": str(target_opr.id)},
        context={"check_totp": False},
    )
    assert serializer.is_valid() is False
    assert errors_payload(serializer.errors) == {
        "non_field_errors": [{"detail": NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED, "code": "invalid"}],
    }
    mock_portone_req_cancel_payment.assert_not_called()
