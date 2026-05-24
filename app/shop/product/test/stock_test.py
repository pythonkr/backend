from datetime import datetime, timezone

import pytest
from freezegun import freeze_time
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.product.models import Option, OptionGroup, Product, Tag


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_current_status_returns_out_of_visible_period_when_before_visible_window(product):
    # _FAR_PAST=2020 이전 (2010) → OUT_OF_VISIBLE_PERIOD.
    assert product.current_status == Product.CurrentStatus.OUT_OF_VISIBLE_PERIOD


@pytest.mark.django_db
def test_product_current_status_returns_out_of_orderable_period_when_outside_orderable_window(product):
    # visible 윈도우는 통과, orderable 윈도우 밖.
    product.orderable_starts_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    product.save()
    assert product.current_status == Product.CurrentStatus.OUT_OF_ORDERABLE_PERIOD


@pytest.mark.django_db
def test_product_current_status_returns_active_when_all_windows_satisfied(product):
    assert product.current_status == Product.CurrentStatus.ACTIVE


@pytest.mark.django_db
def test_product_leftover_stock_returns_none_when_stock_is_zero_unlimited(product):
    # stock=0 → 무한 재고 sentinel.
    product.stock = 0
    product.save()
    assert product.leftover_stock is None


@pytest.mark.django_db
def test_product_leftover_stock_subtracts_paid_and_used_oprs(customer_user, product):
    product.stock = 5
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="a"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="b"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.used,
    )
    refreshed = Product.objects.get(id=product.id)
    assert refreshed.leftover_stock == 3


@pytest.mark.parametrize(
    "ignored_status",
    [OrderProductRelation.OrderProductStatus.pending, OrderProductRelation.OrderProductStatus.refunded],
)
@pytest.mark.django_db
def test_product_leftover_stock_ignores_non_purchased_oprs(customer_user, product, ignored_status):
    product.stock = 5
    product.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="order"),
        product=product,
        price=product.price,
        status=ignored_status,
    )
    refreshed = Product.objects.get(id=product.id)
    assert refreshed.leftover_stock == 5


@pytest.mark.django_db
def test_product_leftover_stock_excludes_single_product_cart_oprs(customer_user, product):
    product.stock = 5
    product.save()
    opr = OrderProductRelation.objects.create(
        product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    SingleProductCart.objects.create(user=customer_user, order_product_relation=opr)
    # cart 단계의 paid OPR 은 차감 안 됨 — to_order() 로 promote 된 후에만 차감 대상.
    refreshed = Product.objects.get(id=product.id)
    assert refreshed.leftover_stock == 5


@pytest.mark.django_db
def test_product_taken_count_returns_zero_when_no_flags(customer_user, product):
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"), product=product, price=product.price
    )
    assert product.get_user_taken_stock_count(user=customer_user, include_cart=False, include_purchased=False) == 0


@pytest.mark.parametrize(
    ("include_cart", "include_purchased", "expected"),
    [
        (True, False, 1),  # pending 만.
        (False, True, 2),  # paid + used.
        (True, True, 3),  # 전체.
    ],
)
@pytest.mark.django_db
def test_product_taken_count_per_flag_combination(customer_user, product, include_cart, include_purchased, expected):
    # refunded 는 모든 flag 조합에서 카운트 안 됨 — 결과 expected 가 4 가 아닌 3 인 것이 그 증거.
    for status in (
        OrderProductRelation.OrderProductStatus.pending,
        OrderProductRelation.OrderProductStatus.paid,
        OrderProductRelation.OrderProductStatus.used,
        OrderProductRelation.OrderProductStatus.refunded,
    ):
        OrderProductRelation.objects.create(
            order=Order.objects.create(user=customer_user, name="order"),
            product=product,
            price=product.price,
            status=status,
        )
    assert (
        product.get_user_taken_stock_count(
            user=customer_user, include_cart=include_cart, include_purchased=include_purchased
        )
        == expected
    )


@pytest.mark.django_db
def test_product_taken_count_isolates_per_user(customer_user, other_user, product):
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="other"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    assert product.get_user_taken_stock_count(user=customer_user, include_cart=True, include_purchased=True) == 0


@pytest.mark.django_db
def test_tag_leftover_stock_returns_none_when_unlimited(tag):
    assert tag.stock == 0
    assert tag.leftover_stock is None


@pytest.mark.django_db
def test_tag_leftover_stock_sums_across_all_tagged_products(customer_user, tag, product):
    tag.stock = 3
    tag.save()
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="paid"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    refreshed = Tag.objects.get(id=tag.id)
    assert refreshed.leftover_stock == 2


@pytest.mark.django_db
def test_tag_taken_count_counts_only_target_user(customer_user, other_user, tag, product):
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="my"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=other_user, name="other"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    assert tag.get_user_taken_stock_count(user=customer_user, include_cart=False, include_purchased=True) == 1


@pytest.mark.django_db
def test_option_leftover_stock_returns_none_when_unlimited(option):
    assert option.stock == 0
    assert option.leftover_stock is None


@pytest.mark.parametrize(
    "purchased_status",
    [OrderProductRelation.OrderProductStatus.paid, OrderProductRelation.OrderProductStatus.used],
)
@pytest.mark.django_db
def test_option_leftover_stock_subtracts_purchased_option_relations(
    customer_user, option_group, option, purchased_status
):
    option.stock = 3
    option.save()
    opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="order"),
        product=option_group.product,
        price=option_group.product.price,
        status=purchased_status,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=option_group, product_option=option
    )
    refreshed = Option.objects.get(id=option.id)
    assert refreshed.leftover_stock == 2


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_option_group_effective_orderable_falls_back_to_product_when_null(product):
    # 그룹 자체 값 None → Product 의 값 fallback. Product 의 fixture orderable 윈도우는 FAR_PAST~FAR_FUTURE.
    group = OptionGroup.objects.create(product=product, name="size")
    assert group.effective_orderable_period.starts_at == product.orderable_starts_at
    assert group.effective_orderable_period.ends_at == product.orderable_ends_at
    assert group.is_orderable_now() is True


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_option_group_is_orderable_now_false_when_group_window_in_future(product):
    group = OptionGroup.objects.create(
        product=product, name="late", orderable_starts_at=datetime(2031, 1, 1, tzinfo=timezone.utc)
    )
    assert group.is_orderable_now() is False


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_option_group_effective_visible_falls_back_to_product_when_null(product):
    group = OptionGroup.objects.create(product=product, name="size")
    assert group.effective_visible_period.starts_at == product.visible_starts_at
    assert group.effective_visible_period.ends_at == product.visible_ends_at
    assert group.is_visible_now() is True


@freeze_time(datetime(2030, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_option_group_is_visible_now_false_when_group_visible_in_future(product):
    group = OptionGroup.objects.create(
        product=product, name="후공개", visible_starts_at=datetime(2031, 1, 1, tzinfo=timezone.utc)
    )
    assert group.is_visible_now() is False


@pytest.mark.django_db
def test_option_group_taken_count_excludes_soft_deleted_opr(customer_user, option_group, option):
    # P2-B: 사용자가 cart 에서 OPR 을 soft-delete 한 경우 group 인당 한도 카운트에 포함되면 안 된다.
    opr = OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="cart"),
        product=option_group.product,
        price=option_group.product.price,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=option_group, product_option=option
    )
    opr.delete()  # soft-delete

    assert option_group.get_user_taken_stock_count(user=customer_user, include_cart=True, include_purchased=False) == 0


@pytest.mark.django_db
def test_option_taken_count_per_flag_excludes_single_product_cart(customer_user, option_group, option):
    cart_opr = OrderProductRelation.objects.create(
        product=option_group.product,
        price=option_group.product.price,
        status=OrderProductRelation.OrderProductStatus.pending,
    )
    SingleProductCart.objects.create(user=customer_user, order_product_relation=cart_opr)
    OrderProductOptionRelation.objects.create(
        order_product_relation=cart_opr, product_option_group=option_group, product_option=option
    )
    # SingleProductCart 에 매달린 OPR 은 cart count 에서 제외 — promote 전이라 stock 점유 아님.
    assert option.get_user_taken_stock_count(user=customer_user, include_cart=True, include_purchased=False) == 0
