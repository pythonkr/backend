import pytest
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus


@pytest.mark.django_db
def test_latest_per_order_field_returns_most_recent_field_per_order(completed_order):
    # 같은 order 에 3건 PaymentHistory — 가장 최근 1건의 status 만 subquery 로 반환돼야.
    PaymentHistory.objects.create(
        order=completed_order, imp_id="imp_b", status=PaymentHistoryStatus.partial_refunded, price=5000
    )
    latest = PaymentHistory.objects.create(
        order=completed_order, imp_id="imp_c", status=PaymentHistoryStatus.refunded, price=0
    )

    subquery = PaymentHistory.objects.latest_per_order_field("status")
    annotated_order = Order.objects.annotate(current_status=subquery).get(id=completed_order.id)
    assert annotated_order.current_status == latest.status


@pytest.mark.django_db
def test_latest_per_order_field_correlates_per_outer_order(completed_order, customer_user, product):
    # 다른 order 의 PaymentHistory 와 섞이지 않는지 — outer_field 상관관계.
    other_order = Order.objects.create(user=customer_user, name="other")
    OrderProductRelation.objects.create(
        order=other_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    PaymentHistory.objects.create(
        order=other_order, imp_id="imp_other", status=PaymentHistoryStatus.completed, price=product.price
    )

    subquery = PaymentHistory.objects.latest_per_order_field("imp_id")
    rows = {o.id: o.latest_imp for o in Order.objects.annotate(latest_imp=subquery).filter(user=customer_user)}
    assert rows[completed_order.id] == completed_order.payment_histories.first().imp_id
    assert rows[other_order.id] == "imp_other"
