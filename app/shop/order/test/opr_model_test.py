from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import NotRefundableErrorMessages
from freezegun import freeze_time
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_order_has_no_imp_id(pending_order):
    # PaymentHistory 부재 → latest_imp_id None → ORDER_NOT_REFUNDABLE.
    opr = pending_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_order_status_not_refundable(refunded_order):
    # order.current_status=refunded → ORDER_NOT_REFUNDABLE_STATUS.
    opr = refunded_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_opr_status_not_paid(completed_order):
    # opr.status=used → PRODUCT_STATUS_IS_NOT_PAID.
    opr = completed_order.products.first()
    opr.status = OrderProductRelation.OrderProductStatus.used
    opr.save()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_STATUS_IS_NOT_PAID


@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_opr_not_refundable_reason_when_refund_window_expired(completed_order):
    opr = completed_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_price_is_zero(customer_user, product):
    # paid OPR + price=0 + donation=0 → PRODUCT_PRICE_IS_ZERO.
    order = Order.objects.create(user=customer_user, name="zero")
    opr = OrderProductRelation.objects.create(
        order=order, product=product, price=0, donation_price=0, status=OrderProductRelation.OrderProductStatus.paid
    )
    PaymentHistory.objects.create(order=order, imp_id="imp_z", status=PaymentHistoryStatus.completed, price=0)
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_PRICE_IS_ZERO


@pytest.mark.django_db
def test_opr_not_refundable_reason_returns_none_for_refundable_opr(completed_order):
    opr = completed_order.products.first()
    assert opr.not_refundable_reason is None
