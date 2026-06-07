import pytest
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistoryStatus


@pytest.mark.django_db
def test_to_order_creates_order_with_same_pk_and_hard_deletes_cart(single_product_cart):
    cart_id = single_product_cart.id

    order = single_product_cart.to_order()

    assert order.id == cart_id
    assert isinstance(order, Order)
    # 의도적 hard_delete — soft delete 가 아닌 실제 DELETE 라 row 자체가 없음.
    assert not SingleProductCart.objects.filter(id=cart_id).exists()


@pytest.mark.django_db
def test_to_order_promotes_customer_info_fk(single_product_cart):
    customer_info = CustomerInfo.objects.get(single_product_cart=single_product_cart)

    order = single_product_cart.to_order()

    customer_info.refresh_from_db()
    assert customer_info.order_id == order.id
    assert customer_info.single_product_cart_id is None


@pytest.mark.django_db
def test_to_order_promotes_opr_fk_to_new_order(single_product_cart):
    opr = single_product_cart.order_product_relation

    order = single_product_cart.to_order()

    opr.refresh_from_db()
    assert opr.order_id == order.id


@pytest.mark.django_db
def test_cart_first_paid_price_is_opr_price_plus_donation(customer_user, ticket_product):
    opr = OrderProductRelation.objects.create(product=ticket_product, price=10000, donation_price=2000)
    cart = SingleProductCart.objects.create(user=customer_user, order_product_relation=opr)
    assert cart.first_paid_price == 12000


@pytest.mark.django_db
def test_cart_payment_history_accessors_simulate_pending_order(single_product_cart):
    # SingleProductCart 는 Order 의 read 인터페이스를 흉내내야 함 — view 단에서 두 모델을 같은 DTO 로 받음.
    assert single_product_cart.current_payment_history is None
    assert single_product_cart.current_paid_price == 0
    assert single_product_cart.current_status == PaymentHistoryStatus.pending
    assert single_product_cart.is_cart is True
    assert single_product_cart.payment_histories == []


@pytest.mark.django_db
def test_cart_products_property_exposes_single_opr_as_queryset(single_product_cart):
    assert list(single_product_cart.products) == [single_product_cart.order_product_relation]


@pytest.mark.django_db
def test_cart_name_returns_product_name(single_product_cart, ticket_product):
    assert single_product_cart.name == ticket_product.name
