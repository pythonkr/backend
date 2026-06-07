"""ProductDto > OptionGroupDto / OptionDto 의 leftover_stock_per_user + leftover_stock_info 검증.

각 한도 (Product.max_quantity_per_user / Product.leftover_stock /
OptionGroup.max_quantity_per_user / Option.max_quantity_per_user / Option.leftover_stock)
하나하나가 binding constraint 가 되는 케이스를 분리해서 본다.
"""

import pytest
from rest_framework.status import HTTP_200_OK
from shop.conftest import FAR_FUTURE, FAR_PAST
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.product.models import Option, OptionGroup, Product
from shop.product.serializers.dto import ProductDto
from shop.test.helpers import ProductsApi


@pytest.fixture
def group_with_options(ticket_product) -> tuple[OptionGroup, Option, Option]:
    """1 group with 2 options — 무제한 / 무한 재고 baseline."""
    group = OptionGroup.objects.create(product=ticket_product, name="사이즈")
    a = Option.objects.create(group=group, name="A", additional_price=0)
    b = Option.objects.create(group=group, name="B", additional_price=0)
    return group, a, b


def _serialize_via_api(client, ticket_product) -> dict:
    response = ProductsApi(http_client=client).retrieve(ticket_product.id)
    assert response.status_code == HTTP_200_OK
    return response.json()


def _add_to_cart(user, ticket_product, option, *, status=OrderProductRelation.OrderProductStatus.pending) -> None:
    order = Order.objects.create(user=user, name=f"o-{user.id}")
    opr = OrderProductRelation.objects.create(
        order=order, product=ticket_product, price=ticket_product.price, status=status
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=option.group, product_option=option, custom_response=""
    )


@pytest.mark.django_db
def test_anonymous_user_sees_full_limits_only(anon_client, ticket_product, group_with_options):
    # 익명 — purchase/cart 누적 0 가정, 한도만 반영. 0 = 무제한 sentinel → None.
    group, a, _b = group_with_options
    group.max_quantity_per_user = 5
    group.save()
    a.max_quantity_per_user = 3
    a.save()

    data = _serialize_via_api(anon_client, ticket_product)
    [grp] = data["option_groups"]
    assert grp["leftover_stock_per_user"] == 5  # group 한도가 binding (ticket_product / stock 무제한)
    assert grp["leftover_stock_info"] == {
        "product_max_quantity_per_user": None,
        "product_leftover_stock": 100,  # fixture stock=100
        "option_group_max_quantity_per_user": 5,
    }
    option_a = next(o for o in grp["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_per_user"] == 3  # option 한도(3) 가 group(5) 보다 작아 binding
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 3
    assert option_a["leftover_stock_info"]["option_group_max_quantity_per_user"] == 5


@pytest.mark.django_db
def test_breakdown_subtracts_cart_and_purchased_for_logged_in_user(
    customer_client, customer_user, ticket_product, group_with_options
):
    # 동일 user 의 cart 1건 + 결제완료 1건 → group 한도 5 - 2 = 3, option 한도 3 - 2 = 1.
    group, a, _b = group_with_options
    group.max_quantity_per_user = 5
    group.save()
    a.max_quantity_per_user = 3
    a.save()

    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.pending)
    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.paid)

    data = _serialize_via_api(customer_client, ticket_product)
    [grp] = data["option_groups"]
    assert grp["leftover_stock_info"]["option_group_max_quantity_per_user"] == 3
    assert grp["leftover_stock_per_user"] == 3

    option_a = next(o for o in grp["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 1
    assert option_a["leftover_stock_info"]["option_group_max_quantity_per_user"] == 3
    assert option_a["leftover_stock_per_user"] == 1  # option 한도 가 binding


@pytest.mark.django_db
def test_product_level_limit_can_be_binding_constraint(
    customer_client, customer_user, ticket_product, group_with_options
):
    # Product.max_quantity_per_user 가 group / option 한도 보다 작아서 binding 이 되는 경우 — 명시적 케이스.
    ticket_product.max_quantity_per_user = 2
    ticket_product.save()
    group, a, _b = group_with_options
    group.max_quantity_per_user = 10
    group.save()
    a.max_quantity_per_user = 10
    a.save()

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["product_max_quantity_per_user"] == 2
    assert option_a["leftover_stock_info"]["option_group_max_quantity_per_user"] == 10
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 10
    assert option_a["leftover_stock_per_user"] == 2  # ticket_product 한도가 binding


@pytest.mark.django_db
def test_option_leftover_stock_propagates_to_breakdown(
    customer_client, customer_user, ticket_product, group_with_options
):
    group, a, _b = group_with_options
    a.stock = 4
    a.save()
    # 다른 user 가 1건 결제 → option.leftover_stock = 3 (이 user 와 무관한 글로벌 잔여).
    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.paid)

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["option_leftover_stock"] == 3
    assert option_a["leftover_stock_per_user"] == 3  # option_leftover_stock 이 binding


@pytest.mark.django_db
def test_other_users_cart_does_not_affect_this_user(
    customer_client, customer_user, other_user, ticket_product, group_with_options
):
    # 다른 user 가 cart 에 담은 옵션은 이 user 의 leftover_stock_per_user 에 영향 X.
    group, a, _b = group_with_options
    a.max_quantity_per_user = 2
    a.save()

    _add_to_cart(other_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.pending)
    _add_to_cart(other_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.pending)

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 2


@pytest.mark.django_db
def test_taken_at_or_above_limit_returns_zero_not_negative(
    customer_client, customer_user, ticket_product, group_with_options
):
    # 한도 도달 / 초과 (admin 의 한도 하향) 상황 — clamp to 0, 음수 노출 금지.
    group, a, _b = group_with_options
    a.max_quantity_per_user = 1
    a.save()
    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.paid)
    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.paid)

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 0
    assert option_a["leftover_stock_per_user"] == 0


@pytest.mark.django_db
def test_refunded_orders_do_not_count_toward_user_usage(
    customer_client, customer_user, ticket_product, group_with_options
):
    # refunded 는 PURCHASED_STOCK_STATUS / pending 어디에도 속하지 않아 누적에서 제외돼야 한다.
    group, a, _b = group_with_options
    a.max_quantity_per_user = 3
    a.save()
    _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.refunded)

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 3


@pytest.mark.django_db
def test_list_query_count_is_independent_of_product_and_option_count(
    customer_client, customer_user, ticket_product, django_assert_max_num_queries
):
    # N+1 회귀 가드 — 상품 / 옵션 수가 늘어도 OPR + OPOR 가 각각 1쿼리로 끝나야 한다.
    # 상품 5개 × 그룹 2개 × 옵션 3개 = 30개 옵션. 각각 한 번씩 customer 가 cart 에 담아두고 list 한다.
    extra_products = [
        Product.objects.create(
            category=ticket_product.category,
            name=f"p{i}",
            name_ko=f"p{i}",
            name_en=f"p{i}",
            price=1000,
            stock=100,
            visible_starts_at=FAR_PAST,
            visible_ends_at=FAR_FUTURE,
            orderable_starts_at=FAR_PAST,
            orderable_ends_at=FAR_FUTURE,
            refundable_ends_at=FAR_FUTURE,
        )
        for i in range(4)
    ]
    all_products = [ticket_product, *extra_products]
    for p in all_products:
        for gi in range(2):
            grp = OptionGroup.objects.create(product=p, name=f"g{gi}", max_quantity_per_user=10)
            for oi in range(3):
                opt = Option.objects.create(group=grp, name=f"o{oi}", max_quantity_per_user=5, stock=20)
                _add_to_cart(customer_user, p, opt, status=OrderProductRelation.OrderProductStatus.pending)

    # 옵션 갯수에 비례해 늘어나면 N+1 회귀로 간주.
    with django_assert_max_num_queries(8):
        response = ProductsApi(http_client=customer_client).list()
    assert response.status_code == HTTP_200_OK
    assert len(response.json()) == 5


@pytest.mark.django_db
def test_soft_deleted_options_are_excluded_from_response(customer_client, ticket_product, group_with_options):
    _group, a, b = group_with_options
    a.delete()  # soft delete

    data = _serialize_via_api(customer_client, ticket_product)
    option_ids = {o["id"] for o in data["option_groups"][0]["options"]}
    assert option_ids == {str(b.id)}


@pytest.mark.django_db
def test_custom_response_opor_counts_group_quota_but_no_option(customer_client, customer_user, ticket_product):
    # is_custom_response=True 그룹은 OPOR.product_option=NULL 로 저장됨. user_group_taken 은 +1,
    # global_option_purchased / user_option_taken 은 NULL option_id 분기로 건너뛰어야 한다.
    custom_group = OptionGroup.objects.create(
        product=ticket_product,
        name="응답",
        max_quantity_per_user=3,
        is_custom_response=True,
        custom_response_pattern=".*",
    )
    order = Order.objects.create(user=customer_user, name="o")
    opr = OrderProductRelation.objects.create(
        order=order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr, product_option_group=custom_group, product_option=None, custom_response="hello"
    )

    data = _serialize_via_api(customer_client, ticket_product)
    grp = next(g for g in data["option_groups"] if g["id"] == str(custom_group.id))
    assert grp["leftover_stock_info"]["option_group_max_quantity_per_user"] == 2  # 3 - 1
    assert grp["leftover_stock_per_user"] == 2


@pytest.mark.django_db
def test_single_product_cart_opr_is_excluded_from_counts(
    customer_client, customer_user, ticket_product, group_with_options
):
    # SingleProductCart 에 attach 된 OPR/OPOR 은 leftover 계산에서 제외 — 직접 결제 경로는 별도 한도라.
    _group, a, _b = group_with_options
    a.max_quantity_per_user = 2
    a.stock = 5
    a.save()
    # SPC OPR (order=None) 1건 + OPOR 1건.
    spc_opr = OrderProductRelation.objects.create(
        product=ticket_product, price=ticket_product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    SingleProductCart.objects.create(user=customer_user, order_product_relation=spc_opr)
    OrderProductOptionRelation.objects.create(
        order_product_relation=spc_opr, product_option_group=a.group, product_option=a, custom_response=""
    )

    data = _serialize_via_api(customer_client, ticket_product)
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    # SPC 가 포함되면 user_option_taken=1 → leftover 1 / global_option_purchased=1 → option_leftover_stock 4.
    # 제외돼야 하므로 한도 그대로.
    assert option_a["leftover_stock_info"]["option_max_quantity_per_user"] == 2
    assert option_a["leftover_stock_info"]["option_leftover_stock"] == 5


@pytest.mark.django_db
def test_direct_dto_instantiation_falls_back_to_model_property(customer_user, ticket_product, group_with_options):
    # context 미주입 시 StockContext 안의 covered_product_ids 가 비어있어 글로벌 잔여 재고 계산이
    # raw stock 으로 빠지지 않도록 (raw 는 글로벌 구매가 안 빠져 잘못된 값). model cached_property 가 정답.
    _group, a, _b = group_with_options
    a.stock = 10
    a.save()
    # 다른 user 가 3건 결제 → 글로벌 leftover_stock = 7.
    for _ in range(3):
        _add_to_cart(customer_user, ticket_product, a, status=OrderProductRelation.OrderProductStatus.paid)

    data = ProductDto(instance=ticket_product).data
    option_a = next(o for o in data["option_groups"][0]["options"] if o["id"] == str(a.id))
    assert option_a["leftover_stock"] == 7
    assert option_a["leftover_stock_info"]["option_leftover_stock"] == 7


@pytest.mark.django_db
def test_all_unlimited_returns_none(anon_client, ticket_product, group_with_options):
    # 모든 한도가 무제한 + 모든 stock 이 무한 → leftover_stock_per_user = None.
    ticket_product.stock = 0
    ticket_product.save()
    data = _serialize_via_api(anon_client, ticket_product)
    [grp] = data["option_groups"]
    assert grp["leftover_stock_per_user"] is None
    assert grp["leftover_stock_info"] == {
        "product_max_quantity_per_user": None,
        "product_leftover_stock": None,
        "option_group_max_quantity_per_user": None,
    }
    option = grp["options"][0]
    assert option["leftover_stock_per_user"] is None
