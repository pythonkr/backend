import uuid
from unittest.mock import patch

import pytest
from core.const.shop_error_messages import CartNotOrderableErrorMessages, ProductNotOrderableErrorMessages
from core.util.testutil import errors_payload
from rest_framework.exceptions import ValidationError
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart, TicketInfo
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.payment_history.services import complete_free_checkout


@pytest.mark.django_db
def test_complete_free_checkout_marks_order_paid_and_records_zero_payment(customer_user, non_ticket_product):
    order = Order.objects.create(user=customer_user, name="free")
    OrderProductRelation.objects.create(order=order, product=non_ticket_product, price=0)
    order.prepare_payment()

    with (
        patch("shop.payment_history.services.transaction.on_commit") as mock_on_commit,
        patch("shop.payment_history.services.send_payment_completed_notifications.delay") as mock_delay,
    ):
        completed = complete_free_checkout(order)
        mock_on_commit.assert_called_once()
        mock_on_commit.call_args.args[0]()

    assert completed.id == order.id
    assert list(completed.products.values_list("status", flat=True)) == [OrderProductRelation.OrderProductStatus.paid]
    assert completed.current_status == PaymentHistoryStatus.completed
    assert completed.current_paid_price == 0
    payment_history = PaymentHistory.objects.get(order=completed)
    assert payment_history.status == PaymentHistoryStatus.completed
    assert payment_history.price == 0
    assert payment_history.imp_id is None
    mock_delay.assert_called_once_with(str(order.id))


@pytest.mark.django_db
def test_complete_free_checkout_promotes_single_product_cart(single_product_cart, option):
    product = single_product_cart.order_product_relation.product
    product.price = 0
    product.donation_allowed = True
    product.save(update_fields=["price", "donation_allowed"])
    single_product_cart.order_product_relation.price = 0
    single_product_cart.order_product_relation.donation_price = 0
    single_product_cart.order_product_relation.save(update_fields=["price", "donation_price"])
    OrderProductOptionRelation.objects.create(
        order_product_relation=single_product_cart.order_product_relation,
        product_option_group=option.group,
        product_option=option,
        custom_response=None,
    )
    TicketInfo.objects.create(
        order_product_relation=single_product_cart.order_product_relation,
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
        contribution_message="응원합니다",
    )
    single_product_cart.prepare_payment()
    cart_id = single_product_cart.id

    with (
        patch("shop.payment_history.services.transaction.on_commit") as mock_on_commit,
        patch("shop.payment_history.services.send_payment_completed_notifications.delay") as mock_delay,
    ):
        completed = complete_free_checkout(single_product_cart)
        mock_on_commit.assert_called_once()
        mock_on_commit.call_args.args[0]()

    assert completed.id == cart_id
    assert Order.objects.filter(id=cart_id).exists()
    assert not SingleProductCart.objects.filter(id=cart_id).exists()
    completed_opr = completed.products.select_related("ticket_info").prefetch_related("options").get()
    assert completed_opr.status == OrderProductRelation.OrderProductStatus.paid
    assert completed_opr.price == 0
    assert completed_opr.donation_price == 0
    ticket_info = completed_opr.ticket_info
    assert ticket_info.name == "김참가"
    assert ticket_info.phone == "010-9999-8888"
    assert ticket_info.email == "attendee@example.com"
    assert ticket_info.organization == "PSK"
    assert ticket_info.contribution_message == "응원합니다"
    option_rel = completed_opr.options.get()
    assert option_rel.product_option_group_id == option.group_id
    assert option_rel.product_option_id == option.id
    assert option_rel.custom_response is None
    assert PaymentHistory.objects.filter(
        order=completed,
        status=PaymentHistoryStatus.completed,
        price=0,
        imp_id=None,
    ).exists()
    mock_delay.assert_called_once_with(str(cart_id))


@pytest.mark.django_db
def test_complete_free_checkout_rejects_empty_zero_price_order(customer_user):
    order = Order.objects.create(user=customer_user, name="empty")
    order.prepare_payment()

    with (
        patch("shop.payment_history.services.transaction.on_commit") as mock_on_commit,
        pytest.raises(ValidationError) as exc_info,
    ):
        complete_free_checkout(order)

    assert errors_payload(exc_info.value.detail) == {
        "non_field_errors": [{"detail": CartNotOrderableErrorMessages.EMPTY, "code": "invalid"}]
    }
    assert PaymentHistory.objects.filter(order=order).count() == 0
    mock_on_commit.assert_not_called()


@pytest.mark.django_db
def test_complete_free_checkout_rechecks_stock_after_single_cart_preparation(single_product_cart, other_user):
    product = single_product_cart.order_product_relation.product
    product.price = 0
    product.stock = 1
    product.save(update_fields=["price", "stock"])
    single_product_cart.order_product_relation.price = 0
    single_product_cart.order_product_relation.save(update_fields=["price"])
    TicketInfo.objects.create(
        order_product_relation=single_product_cart.order_product_relation,
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
    )
    single_product_cart.prepare_payment()
    completed_order = Order.objects.create(user=other_user, name="already paid")
    OrderProductRelation.objects.create(
        order=completed_order,
        product=product,
        price=0,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    PaymentHistory.objects.create(
        order=completed_order,
        imp_id=None,
        status=PaymentHistoryStatus.completed,
        price=0,
    )

    with (
        patch("shop.payment_history.services.transaction.on_commit") as mock_on_commit,
        pytest.raises(ValidationError) as exc_info,
    ):
        complete_free_checkout(single_product_cart)

    assert ProductNotOrderableErrorMessages.SOLDOUT.format(product.name) in str(exc_info.value.detail)
    assert PaymentHistory.objects.filter(order_id=single_product_cart.id).count() == 0
    assert SingleProductCart.objects.filter(id=single_product_cart.id).exists()
    mock_on_commit.assert_not_called()


@pytest.mark.django_db
def test_complete_free_checkout_rejects_duplicate_single_cart_completion(single_product_cart):
    single_product_cart.order_product_relation.price = 0
    single_product_cart.order_product_relation.save(update_fields=["price"])
    TicketInfo.objects.create(
        order_product_relation=single_product_cart.order_product_relation,
        name="김참가",
        phone="010-9999-8888",
        email="attendee@example.com",
        organization="PSK",
    )
    single_product_cart.prepare_payment()
    cart_id = single_product_cart.id
    complete_free_checkout(single_product_cart)

    with (
        patch("shop.payment_history.services.transaction.on_commit") as mock_on_commit,
        pytest.raises(ValidationError) as exc_info,
    ):
        complete_free_checkout(single_product_cart)

    assert errors_payload(exc_info.value.detail) == [
        {"detail": "이미 처리된 주문이거나 무료 완료로 전환할 수 없습니다.", "code": "invalid"}
    ]
    assert PaymentHistory.objects.filter(order_id=cart_id).count() == 1
    mock_on_commit.assert_not_called()


@pytest.mark.django_db
def test_complete_free_checkout_rejects_positive_amount(order_factory):
    order = order_factory(status="prepared", is_ticket=False)

    with pytest.raises(ValidationError) as exc_info:
        complete_free_checkout(order)

    assert errors_payload(exc_info.value.detail) == [
        {"detail": "무료 주문은 결제 준비 금액이 0원이어야 합니다.", "code": "invalid"}
    ]


@pytest.mark.django_db
def test_complete_free_checkout_rejects_missing_single_cart_target():
    ghost_cart = SingleProductCart(id=uuid.uuid4())

    with pytest.raises(ValidationError) as exc_info:
        complete_free_checkout(ghost_cart)

    assert errors_payload(exc_info.value.detail) == [
        {"detail": "무료 주문 대상을 찾을 수 없습니다.", "code": "invalid"}
    ]
