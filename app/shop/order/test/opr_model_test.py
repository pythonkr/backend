from datetime import datetime, timezone

import pytest
from core.const.shop_error_messages import NotRefundableErrorMessages
from freezegun import freeze_time
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_order_has_no_imp_id(order_factory):
    pending_order = order_factory()
    opr = pending_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_order_status_not_refundable(order_factory):
    refunded_order = order_factory(status="refunded")
    opr = refunded_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_opr_status_not_paid(order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    opr.status = OrderProductRelation.OrderProductStatus.used
    opr.save()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_STATUS_IS_NOT_PAID


@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_opr_not_refundable_reason_when_refund_window_expired(order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_REFUND_TIME_EXPIRED


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_product_not_refundable(ticket_product, order_factory):
    # refundable_ends_at=null → 기간 만료와 무관하게 환불 불가 사유.
    ticket_product.refundable_ends_at = None
    ticket_product.save()
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_IS_NOT_REFUNDABLE


@pytest.mark.django_db
def test_opr_not_refundable_reason_when_price_is_zero(customer_user, ticket_product):
    # paid OPR + price=0 + donation=0 → PRODUCT_PRICE_IS_ZERO.
    order = Order.objects.create(user=customer_user, name="zero")
    opr = OrderProductRelation.objects.create(
        order=order,
        product=ticket_product,
        price=0,
        donation_price=0,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    PaymentHistory.objects.create(order=order, imp_id="imp_z", status=PaymentHistoryStatus.completed, price=0)
    assert opr.not_refundable_reason == NotRefundableErrorMessages.PRODUCT_PRICE_IS_ZERO


@pytest.mark.django_db
def test_opr_not_refundable_reason_returns_none_for_refundable_opr(order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    assert opr.not_refundable_reason is None


def test_build_verify_display_maps_frozen_context():
    assert OrderProductRelation().build_verify_display(
        {
            "event_name": "PyCon Korea",
            "event_date": "2026년 6월 6일(토)",
            "participant_name": "홍길동",
            "organization": "PSK",
            "email": "hong@example.com",
        }
    ) == {
        "참가자명": "홍길동",
        "소속": "PSK",
        "이메일": "hong@example.com",
        "행사명": "PyCon Korea",
        "행사 일시": "2026년 6월 6일(토)",
    }


@pytest.mark.django_db
def test_is_document_downloadable_by_only_order_owner(used_ticket_opr, other_user):
    assert used_ticket_opr.is_document_downloadable_by(used_ticket_opr.order.user) is True
    assert used_ticket_opr.is_document_downloadable_by(other_user) is False


@pytest.mark.django_db
def test_issue_document_rejected_for_invalid_opr(used_ticket_opr):
    # event 연결을 끊으면 is_document_valid=False → 모델 경계 가드가 직접 발급(view 우회)을 막는다.
    category = used_ticket_opr.product.category
    category.event = None
    category.save(update_fields=["event"])
    with pytest.raises(OrderProductRelation.NotIssuableError):
        used_ticket_opr.get_or_issue_document()
