from datetime import datetime, timedelta, timezone

import pytest
from core.const.shop_error_messages import NotRefundableErrorMessages
from freezegun import freeze_time
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus


@pytest.mark.django_db
def test_pending_cart_first_paid_price_sums_products_and_donation(customer_user, ticket_product):
    order = Order.objects.create(user=customer_user, name=ticket_product.name)
    OrderProductRelation.objects.create(order=order, product=ticket_product, price=1000, donation_price=200)
    OrderProductRelation.objects.create(order=order, product=ticket_product, price=3000, donation_price=500)
    assert order.first_paid_price == 1000 + 200 + 3000 + 500


@pytest.mark.django_db
def test_pending_cart_first_paid_price_is_zero_when_no_products(customer_user):
    order = Order.objects.create(user=customer_user, name="empty")
    assert order.first_paid_price == 0


@pytest.mark.django_db
def test_pending_cart_payment_history_accessors_return_none_when_no_history(order_factory):
    pending_order = order_factory()
    assert pending_order.first_payment_history is None
    assert pending_order.first_paid_at is None
    assert pending_order.current_payment_history is None
    assert pending_order.current_paid_price == 0
    assert pending_order.current_status == PaymentHistoryStatus.pending
    assert pending_order.latest_imp_id is None
    assert pending_order.is_cart is True


@pytest.mark.django_db
def test_first_payment_history_returns_oldest_among_multiple(order_factory):
    completed_order = order_factory(status="completed")
    completed = completed_order.payment_histories.first()
    PaymentHistory.objects.create(
        order=completed_order, imp_id="imp_test_completed", status=PaymentHistoryStatus.refunded, price=0
    )
    # cached_property bust 를 위해 인스턴스 재조회.
    refreshed = Order.objects.get(id=completed_order.id)
    assert refreshed.first_payment_history.id == completed.id
    assert refreshed.first_paid_at == completed.created_at


@pytest.mark.django_db
def test_current_payment_history_returns_newest_among_multiple(order_factory):
    completed_order = order_factory(status="completed")
    refund_ph = PaymentHistory.objects.create(
        order=completed_order, imp_id="imp_test_completed", status=PaymentHistoryStatus.refunded, price=0
    )
    refreshed = Order.objects.get(id=completed_order.id)
    assert refreshed.current_payment_history.id == refund_ph.id
    assert refreshed.current_status == PaymentHistoryStatus.refunded
    assert refreshed.current_paid_price == 0
    assert refreshed.latest_imp_id == "imp_test_completed"
    assert refreshed.is_cart is False


@pytest.mark.django_db
def test_payment_history_accessors_use_prefetched_attr_when_present(order_factory):
    pending_order = order_factory()
    ph1 = PaymentHistory.objects.create(
        order=pending_order, imp_id="imp_a", status=PaymentHistoryStatus.completed, price=10000
    )
    ph2 = PaymentHistory.objects.create(
        order=pending_order, imp_id="imp_b", status=PaymentHistoryStatus.refunded, price=0
    )

    prefetched = Order.objects.prefetch_related(Order.prefetchs["_active_payment_histories"]).get(id=pending_order.id)
    assert prefetched.current_payment_history.id == ph2.id
    assert prefetched.first_payment_history.id == ph1.id


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_no_imp_id(order_factory):
    pending_order = order_factory()
    assert pending_order.not_fully_refundable_reason == NotRefundableErrorMessages.ORDER_IMP_ID_NOT_EXIST


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_order_status_not_refundable(order_factory):
    refunded_order = order_factory(status="refunded")
    assert refunded_order.not_fully_refundable_reason == NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE_STATUS


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_any_opr_is_pending(ticket_product, order_factory):
    completed_order = order_factory(status="completed")
    OrderProductRelation.objects.create(order=completed_order, product=ticket_product, price=ticket_product.price)
    refreshed = Order.objects.get(id=completed_order.id)
    assert (
        refreshed.not_fully_refundable_reason
        == NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_USED_TRY_AFTER_CHANGING_STATUS
    )


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_any_opr_is_used(order_factory):
    completed_order = order_factory(status="completed")
    completed_order.products.update(status=OrderProductRelation.OrderProductStatus.used)
    refreshed = Order.objects.get(id=completed_order.id)
    assert (
        refreshed.not_fully_refundable_reason
        == NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_USED_TRY_AFTER_CHANGING_STATUS
    )


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_no_paid_product(order_factory):
    completed_order = order_factory(status="completed")
    completed_order.products.update(status=OrderProductRelation.OrderProductStatus.refunded)
    refreshed = Order.objects.get(id=completed_order.id)
    assert refreshed.not_fully_refundable_reason == NotRefundableErrorMessages.ORDER_REFUNDABLE_PRODUCT_NOT_FOUND


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_price_zero(customer_user, ticket_product):
    order = Order.objects.create(user=customer_user, name="zero")
    OrderProductRelation.objects.create(
        order=order,
        product=ticket_product,
        price=0,
        donation_price=0,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    PaymentHistory.objects.create(order=order, imp_id="imp_zero", status=PaymentHistoryStatus.completed, price=0)
    refreshed = Order.objects.get(id=order.id)
    assert refreshed.not_fully_refundable_reason == NotRefundableErrorMessages.ORDER_REFUNDABLE_PRICE_NOT_FOUND


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_expected_price_mismatch(ticket_product, order_factory):
    completed_order = order_factory(status="completed")
    OrderProductRelation.objects.create(
        order=completed_order, product=ticket_product, price=5000, status=OrderProductRelation.OrderProductStatus.paid
    )
    refreshed = Order.objects.get(id=completed_order.id)
    assert refreshed.not_fully_refundable_reason == NotRefundableErrorMessages.ORDER_REFUND_TARGET_PRICE_IS_MISMATCH


@freeze_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_not_fully_refundable_reason_when_refund_window_expired(order_factory):
    completed_order = order_factory(status="completed")
    assert completed_order.not_fully_refundable_reason == NotRefundableErrorMessages.ONE_OF_PRODUCT_REFUND_TIME_EXPIRED


@pytest.mark.django_db
def test_not_fully_refundable_reason_when_product_not_refundable(ticket_product, order_factory):
    # refundable_ends_at=null → 기간 만료와 무관하게 환불 불가 사유.
    ticket_product.refundable_ends_at = None
    ticket_product.save()
    completed_order = order_factory(status="completed")
    assert completed_order.not_fully_refundable_reason == NotRefundableErrorMessages.ONE_OF_PRODUCT_IS_NOT_REFUNDABLE


@pytest.mark.django_db
def test_not_fully_refundable_reason_returns_none_for_refundable_order(order_factory):
    completed_order = order_factory(status="completed")
    assert completed_order.not_fully_refundable_reason is None


@pytest.mark.django_db
def test_filter_has_payment_histories_includes_only_orders_with_payment(customer_user, order_factory):
    completed_order = order_factory(status="completed")
    cart = Order.objects.create(user=customer_user, name="cart")
    qs = Order.objects.filter_has_payment_histories().filter(user=customer_user)
    ids = list(qs.values_list("id", flat=True))
    assert ids == [completed_order.id]
    assert cart.id not in ids


@pytest.mark.django_db
def test_filter_has_no_payment_histories_includes_only_carts(customer_user, order_factory):
    completed_order = order_factory(status="completed")
    cart = Order.objects.create(user=customer_user, name="cart")
    qs = Order.objects.filter_has_no_payment_histories().filter(user=customer_user)
    ids = list(qs.values_list("id", flat=True))
    assert ids == [cart.id]
    assert completed_order.id not in ids


@pytest.mark.django_db
def test_filter_purchased_by_returns_only_target_users_purchased_orders(
    customer_user, other_user, ticket_product, order_factory
):
    completed_order = order_factory(status="completed")
    other_order = Order.objects.create(user=other_user, name="other")
    OrderProductRelation.objects.create(
        order=other_order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    PaymentHistory.objects.create(
        order=other_order, imp_id="imp_other", status=PaymentHistoryStatus.completed, price=ticket_product.price
    )

    qs = Order.objects.filter_purchased_by(customer_user)
    ids = list(qs.values_list("id", flat=True))
    assert ids == [completed_order.id]


@pytest.mark.django_db
def test_filter_purchased_by_excludes_pending_status_orders(customer_user, order_factory):
    pending_order = order_factory()
    qs = Order.objects.filter_purchased_by(customer_user)
    assert pending_order.id not in list(qs.values_list("id", flat=True))


@freeze_time(datetime(2026, 5, 23, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_filter_in_last_six_months_excludes_orders_older_than_183_days(customer_user):
    fresh = Order.objects.create(user=customer_user, name="fresh")
    stale = Order.objects.create(user=customer_user, name="stale")
    # auto_now_add 우회를 위한 raw update.
    Order.objects.filter(id=stale.id).update(
        created_at=datetime(2026, 5, 23, tzinfo=timezone.utc) - timedelta(days=200)
    )

    qs = Order.objects.filter_in_last_six_months().filter(user=customer_user)
    ids = list(qs.values_list("id", flat=True))
    assert fresh.id in ids
    assert stale.id not in ids
