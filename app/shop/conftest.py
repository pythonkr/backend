from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from core.external_apis.portone.client import portone_client
from django.test import override_settings
from rest_framework.test import APIClient
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, ProductTagRelation, Tag
from user.models import UserExt

# Product 모델 datetime default 인 naive datetime.min / max 는 Asia/Seoul → UTC 변환 시 Postgres timestamptz 범위 밖으로 나가 깨진다.
# fixture 는 항상 tz-aware 명시값으로 생성.
FAR_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)
FAR_FUTURE = datetime(2099, 12, 31, tzinfo=timezone.utc)

# 같은 주문의 PaymentHistory 는 동일 PortOne 거래에서 파생되므로 imp_id 가 공유된다.
_COMPLETED_ORDER_IMP_ID = "imp_test_completed"

# webhook IP allowlist 통과용 — webhook 테스트는 이 IP 를 REMOTE_ADDR 로 사용.
WEBHOOK_WHITELISTED_IP = "1.2.3.4"


@pytest.fixture(autouse=True)
def _portone_settings():
    """shop 전체 테스트 — DEBUG off + PortOne IP allowlist + mock 가능한 dummy 키 / URL.

    실제 PortOne SDK 호출은 `mock_portone_*` fixture 가 가로채므로 키 값은 임의.
    `override_settings` 라 각 테스트가 별도 override 하면 그쪽이 우선.
    """
    with override_settings(
        DEBUG=False,
        PORTONE=SimpleNamespace(
            api_url="https://api.example-portone.kr",
            ip_list=[WEBHOOK_WHITELISTED_IP],
            imp_key="portone_api_key",
            imp_secret="portone_api_secret",  # nosec: B106
        ),
    ):
        yield


@pytest.fixture
def customer_user(db) -> UserExt:
    return UserExt.objects.create_user(username="buyer", email="buyer@example.com")


@pytest.fixture
def other_user(db) -> UserExt:
    """`customer_user` 와 무관한 또 다른 일반 user — 권한/소유권 boundary 테스트용."""
    return UserExt.objects.create_user(username="other", email="other@example.com")


@pytest.fixture
def staff_user(db) -> UserExt:
    return UserExt.objects.create_superuser(username="staff", email="staff@example.com")


@pytest.fixture
def anon_client() -> APIClient:
    return APIClient()


@pytest.fixture
def customer_client(customer_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=customer_user)
    return client


@pytest.fixture
def other_client(other_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client


@pytest.fixture
def staff_client(staff_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


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
        visible_starts_at=FAR_PAST,
        visible_ends_at=FAR_FUTURE,
        orderable_starts_at=FAR_PAST,
        orderable_ends_at=FAR_FUTURE,
        refundable_ends_at=FAR_FUTURE,
    )


@pytest.fixture
def donation_product(product) -> Product:
    """`product` fixture 를 donation_allowed=True 로 토글 — patron / 후원 테스트용."""
    product.donation_allowed = True
    product.donation_max_price = 999_999
    product.save()
    return product


@pytest.fixture
def products_by_status(product) -> dict[Product.CurrentStatus, Product]:
    """`Product.CurrentStatus` 4가지 상태별 Product 묶음 — status filter / queryset 테스트용.

    `ACTIVE` 는 fixture `product` 재사용 (visible/orderable 모두 NOW 포함).
    """
    common = {
        "category": product.category,
        "price": 100,
        "visible_starts_at": FAR_PAST,
        "visible_ends_at": FAR_FUTURE,
        "orderable_starts_at": FAR_PAST,
        "orderable_ends_at": FAR_FUTURE,
        "refundable_ends_at": FAR_FUTURE,
    }
    return {
        Product.CurrentStatus.ACTIVE: product,
        Product.CurrentStatus.HIDDEN: Product.objects.create(name="hidden", hidden=True, **common),
        Product.CurrentStatus.OUT_OF_VISIBLE_PERIOD: Product.objects.create(
            **{**common, "visible_starts_at": FAR_FUTURE}, name="oov"
        ),
        Product.CurrentStatus.OUT_OF_ORDERABLE_PERIOD: Product.objects.create(
            **{**common, "orderable_starts_at": FAR_FUTURE}, name="ooo"
        ),
    }


@pytest.fixture
def option_group(product) -> OptionGroup:
    """기본 옵션 그룹 — `is_custom_response=False`, 선택형. `min_quantity_per_product=0` 이라 stock 검사 우회."""
    return OptionGroup.objects.create(product=product, name="사이즈")


@pytest.fixture
def option(option_group) -> Option:
    """`option_group` 의 기본 옵션 — 무한 재고 (stock=0)."""
    return Option.objects.create(group=option_group, name="L", additional_price=0)


@pytest.fixture
def tag(product) -> Tag:
    """기본 태그 — `product` 와 ProductTagRelation 으로 연결. 무한 재고 (stock=0)."""
    t = Tag.objects.create(name="굿즈")
    ProductTagRelation.objects.create(product=product, tag=t)
    return t


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
def empty_cart(customer_user) -> Order:
    """OPR 없는 빈 Order — PaymentHistory 없는 cart 상태."""
    return Order.objects.create(user=customer_user, name="cart")


@pytest.fixture
def donation_completed_order(completed_order, donation_product) -> Order:
    """결제 완료 + OPR 에 donation_price 부여 — patron / 후원 통계 테스트용."""
    completed_order.products.update(donation_price=5000)
    return completed_order


@pytest.fixture
def donation_refunded_order(refunded_order, donation_product) -> Order:
    """전액 환불 + OPR 에 donation_price 부여 — 환불된 후원 주문 boundary 테스트용."""
    refunded_order.products.update(donation_price=5000)
    return refunded_order


@pytest.fixture
def modifiable_option_relation(completed_order, product) -> OrderProductOptionRelation:
    """custom_response 수정 가능 옵션 — `response_modifiable_ends_at` 미래, paid OPR 에 attached."""
    group = OptionGroup.objects.create(
        product=product,
        name="요청사항",
        is_custom_response=True,
        custom_response_pattern=r"^.{1,100}$",
        response_modifiable_ends_at=FAR_FUTURE,
    )
    return OrderProductOptionRelation.objects.create(
        order_product_relation=completed_order.products.first(),
        product_option_group=group,
        custom_response="initial",
    )


@pytest.fixture
def mock_portone_find_payment_info():
    """`portone_client.find_payment_info` 를 mock. 각 테스트에서 `.return_value` 를 덮어쓴다."""
    with patch.object(portone_client, "find_payment_info") as mocked:
        yield mocked


@pytest.fixture
def mock_portone_req_cancel_payment():
    """`portone_client.req_cancel_payment` 를 mock — 환불 호출 검증 / 실패 주입에 사용."""
    with patch.object(portone_client, "req_cancel_payment") as mocked:
        yield mocked


@pytest.fixture
def mock_portone_register():
    """`portone_client.register_or_update_prepared_payment` 를 mock — 결제 사전 등록 호출 검증."""
    with patch.object(portone_client, "register_or_update_prepared_payment") as mocked:
        yield mocked


@pytest.fixture
def mock_portone_kcp_receipt():
    """`portone_client.get_kcp_receipt_search_data` 를 mock — 영수증 페이지 redirect 데이터 주입."""
    with patch.object(portone_client, "get_kcp_receipt_search_data") as mocked:
        yield mocked


@pytest.fixture
def mocked_on_commit():
    # test transaction 은 rollback 되므로 on_commit callback 이 실제로 fire 안 됨 — 등록만 검증.
    with patch("shop.payment_history.serializers.transaction.on_commit") as mocked:
        yield mocked
