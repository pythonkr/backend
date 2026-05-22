from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from core.external_apis.portone.client import portone_client
from shop.order.models import CustomerInfo, Order, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Category, CategoryGroup, Product
from user.models import UserExt

# Product 모델 datetime default 인 naive datetime.min / max 는 Asia/Seoul → UTC 변환 시 Postgres timestamptz 범위 밖으로 나가 깨진다.
# fixture 는 항상 tz-aware 명시값으로 생성.
_FAR_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)
_FAR_FUTURE = datetime(2099, 12, 31, tzinfo=timezone.utc)

# 같은 주문의 PaymentHistory 는 동일 PortOne 거래에서 파생되므로 imp_id 가 공유된다.
_COMPLETED_ORDER_IMP_ID = "imp_test_completed"


@pytest.fixture
def customer_user(db) -> UserExt:
    return UserExt.objects.create_user(username="buyer", email="buyer@example.com")


@pytest.fixture
def staff_user(db) -> UserExt:
    return UserExt.objects.create_superuser(username="staff", email="staff@example.com")


@pytest.fixture
def product(db) -> Product:
    # category_group / category 는 Product 의 FK 체인을 만들기 위한 중간 단계 — 직접 참조하는 테스트가 생기는 시점에 별도 fixture 로 분리.
    category_group = CategoryGroup.objects.create(name="기본")
    category = Category.objects.create(group=category_group, name="티켓")
    return Product.objects.create(
        category=category,
        name="파이콘 한국 2026 티켓",
        name_ko="파이콘 한국 2026 티켓",
        name_en="PyCon Korea 2026 Ticket",
        price=10000,
        stock=100,
        visible_starts_at=_FAR_PAST,
        visible_ends_at=_FAR_FUTURE,
        orderable_starts_at=_FAR_PAST,
        orderable_ends_at=_FAR_FUTURE,
        refundable_ends_at=_FAR_FUTURE,
    )


@pytest.fixture
def pending_order(customer_user, product) -> Order:
    """결제 직전 cart 상태 — PaymentHistory 없음, OPR pending."""
    order = Order.objects.create(
        user=customer_user, name=product.name, name_ko=product.name_ko, name_en=product.name_en
    )
    OrderProductRelation.objects.create(order=order, product=product, price=product.price)
    CustomerInfo.objects.create(order=order, name="홍길동", phone="01012345678", email="customer@example.com")
    return order


@pytest.fixture
def single_product_cart(customer_user, product) -> SingleProductCart:
    """단일 상품 결제용 임시 cart — `to_order()` 로 같은 PK Order 로 승격됨."""
    opr = OrderProductRelation.objects.create(product=product, price=product.price)
    cart = SingleProductCart.objects.create(user=customer_user, order_product_relation=opr)
    CustomerInfo.objects.create(
        single_product_cart=cart, name="홍길동", phone="01012345678", email="customer@example.com"
    )
    return cart


@pytest.fixture
def completed_order(pending_order) -> Order:
    """결제 완료 — OPR paid + PaymentHistory completed."""
    pending_order.products.update(status=OrderProductRelation.OrderProductStatus.paid)
    PaymentHistory.objects.create(
        order=pending_order,
        imp_id=_COMPLETED_ORDER_IMP_ID,
        status=PaymentHistoryStatus.completed,
        price=pending_order.first_paid_price,
    )
    return pending_order


@pytest.fixture
def refunded_order(completed_order) -> Order:
    """전액 환불된 주문 — PaymentHistory(refunded, price=0) 추가."""
    completed_order.products.update(status=OrderProductRelation.OrderProductStatus.refunded)
    PaymentHistory.objects.create(
        order=completed_order,
        imp_id=_COMPLETED_ORDER_IMP_ID,
        status=PaymentHistoryStatus.refunded,
        price=0,
    )
    return completed_order


@pytest.fixture
def partial_refunded_order(completed_order) -> Order:
    """부분 환불된 주문 — PaymentHistory(partial_refunded) 추가."""
    PaymentHistory.objects.create(
        order=completed_order,
        imp_id=_COMPLETED_ORDER_IMP_ID,
        status=PaymentHistoryStatus.partial_refunded,
        price=completed_order.first_paid_price // 2,
    )
    return completed_order


@pytest.fixture
def mock_portone_find_payment_info():
    """`portone_client.find_payment_info` 를 mock. 각 테스트에서 `.return_value` 를 덮어쓴다."""
    with patch.object(portone_client, "find_payment_info") as mocked:
        yield mocked


@pytest.fixture
def mocked_on_commit():
    # test transaction 은 rollback 되므로 on_commit callback 이 실제로 fire 안 됨 — 등록만 검증.
    with patch("shop.payment_history.serializers.transaction.on_commit") as mocked:
        yield mocked
