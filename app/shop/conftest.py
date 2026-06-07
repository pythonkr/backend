from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal
from unittest.mock import DEFAULT, patch

import pytest
from core.external_apis.portone.client import portone_client
from django.test import override_settings
from model_bakery import baker
from rest_framework.test import APIClient
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, ProductTagRelation, Tag
from user.models import UserExt


@contextmanager
def _strict_portone_mock(target_attr: str):
    """`portone_client.<target_attr>` 를 mock 하되, `.return_value` 미설정 시 호출 즉시 RuntimeError.

    Mock 내부 `_mock_return_value` 는 미설정 시 `DEFAULT` sentinel — side_effect 가 이를 검사하면
    "테스트가 명시적으로 return_value 를 세팅했는가" 와 "자동 생성된 MagicMock 인가" 를 구분할 수 있다.
    side_effect 가 `DEFAULT` 를 반환하면 Mock 은 정상 경로로 `return_value` 를 사용하므로 기존 호출부 변경 불요.
    `.side_effect = ...` 를 직접 주입하는 테스트(예: `PortOneException`)는 그대로 동작.
    """
    with patch.object(portone_client, target_attr) as mocked:

        def _strict(*_args, **_kwargs):
            if mocked._mock_return_value is DEFAULT:
                raise RuntimeError(
                    f"PortOne mock `portone_client.{target_attr}` was called without an explicit `.return_value` — "
                    f"set `mock.return_value = ...` before exercising the code under test."
                )
            return DEFAULT

        mocked.side_effect = _strict
        yield mocked


# Product 모델 datetime default 인 naive datetime.min / max 는 Asia/Seoul → UTC 변환 시 Postgres timestamptz 범위 밖으로 나가 깨진다.
# fixture 는 항상 tz-aware 명시값으로 생성.
FAR_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)
FAR_FUTURE = datetime(2099, 12, 31, tzinfo=timezone.utc)

# 같은 주문의 PaymentHistory 는 동일 PortOne 거래에서 파생되므로 imp_id 가 공유된다.
_COMPLETED_ORDER_IMP_ID = "imp_test_completed"

# webhook IP allowlist 통과용 — webhook 테스트는 이 IP 를 REMOTE_ADDR 로 사용.
WEBHOOK_WHITELISTED_IP = "1.2.3.4"

# 티켓 참가자 정보 입력 공용 페이로드.
VALID_TICKET_INFO = {
    "name": "김참가",
    "phone": "010-9999-8888",
    "email": "attendee@example.com",
    "organization": "PSK",
}


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
def ticket_product(db) -> Product:
    category_group = CategoryGroup.objects.create(name="기본")
    category = Category.objects.create(group=category_group, name="티켓", is_ticket=True)
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
def donation_product(ticket_product) -> Product:
    """`ticket_product` fixture 를 donation_allowed=True 로 토글 — patron / 후원 테스트용."""
    ticket_product.donation_allowed = True
    ticket_product.donation_max_price = 999_999
    ticket_product.save()
    return ticket_product


@pytest.fixture
def non_ticket_product(db) -> Product:
    category_group = CategoryGroup.objects.create(name="굿즈군")
    category = Category.objects.create(group=category_group, name="굿즈", is_ticket=False)
    return Product.objects.create(
        category=category,
        name="파이콘 한국 2026 머그컵",
        name_ko="파이콘 한국 2026 머그컵",
        name_en="PyCon Korea 2026 Mug",
        price=10000,
        stock=100,
        visible_starts_at=FAR_PAST,
        visible_ends_at=FAR_FUTURE,
        orderable_starts_at=FAR_PAST,
        orderable_ends_at=FAR_FUTURE,
        refundable_ends_at=FAR_FUTURE,
    )


@pytest.fixture
def products_by_status(ticket_product) -> dict[Product.CurrentStatus, Product]:
    """`Product.CurrentStatus` 4가지 상태별 Product 묶음 — status filter / queryset 테스트용.

    `ACTIVE` 는 fixture `ticket_product` 재사용 (visible/orderable 모두 NOW 포함).
    """
    common = {
        "category": ticket_product.category,
        "price": 100,
        "visible_starts_at": FAR_PAST,
        "visible_ends_at": FAR_FUTURE,
        "orderable_starts_at": FAR_PAST,
        "orderable_ends_at": FAR_FUTURE,
        "refundable_ends_at": FAR_FUTURE,
    }
    return {
        Product.CurrentStatus.ACTIVE: ticket_product,
        Product.CurrentStatus.OUT_OF_VISIBLE_PERIOD: Product.objects.create(
            **{**common, "visible_starts_at": FAR_FUTURE}, name="oov"
        ),
        Product.CurrentStatus.OUT_OF_ORDERABLE_PERIOD: Product.objects.create(
            **{**common, "orderable_starts_at": FAR_FUTURE}, name="ooo"
        ),
    }


@pytest.fixture
def option_group(ticket_product) -> OptionGroup:
    """기본 옵션 그룹 — `is_custom_response=False`, 선택형. `min_quantity_per_product=0` 이라 stock 검사 우회."""
    return OptionGroup.objects.create(product=ticket_product, name="사이즈")


@pytest.fixture
def option(option_group) -> Option:
    """`option_group` 의 기본 옵션 — 무한 재고 (stock=0)."""
    return Option.objects.create(group=option_group, name="L", additional_price=0)


@pytest.fixture
def tag(ticket_product) -> Tag:
    """기본 태그 — `ticket_product` 와 ProductTagRelation 으로 연결. 무한 재고 (stock=0)."""
    t = Tag.objects.create(name="굿즈")
    ProductTagRelation.objects.create(product=ticket_product, tag=t)
    return t


@pytest.fixture
def single_product_cart(customer_user, ticket_product) -> SingleProductCart:
    """단일 상품 결제용 임시 cart — `to_order()` 로 같은 PK Order 로 승격됨."""
    opr = OrderProductRelation.objects.create(product=ticket_product, price=ticket_product.price)
    cart = SingleProductCart.objects.create(user=customer_user, order_product_relation=opr)
    CustomerInfo.objects.create(
        single_product_cart=cart, name="홍길동", phone="01012345678", email="customer@example.com"
    )
    return cart


OrderStatus = Literal["empty", "cart", "prepared", "completed", "refunded", "partial_refunded"]


@pytest.fixture
def order_factory(request, customer_user):
    """Order 팩토리 — 상태 / 후원 매트릭스를 한 함수로 표현.

    Args:
        status:
            - ``"empty"``: OPR / CustomerInfo 없는 빈 Order (donation 인자 무시)
            - ``"cart"``: PH 없음, OPR pending
            - ``"prepared"``: ``"cart"`` + 결제 준비 snapshot/hash 저장
            - ``"completed"``: PH completed + OPR paid
            - ``"refunded"``: 전액 환불 — PH refunded(price=0) 추가 + OPR refunded
            - ``"partial_refunded"``: 부분 환불 — PH partial_refunded 추가
        donation: OPR 의 ``donation_price`` 금액. ``>0`` 이면 ``donation_product`` (donation_allowed=True) 사용.
        is_ticket: 상품 종류. ``True``(기본)=티켓(``ticket_product``), ``False``=일반(``non_ticket_product``).
            ``donation>0`` 이면 종류와 무관하게 ``donation_product`` 사용.
    """

    def make(*, status: OrderStatus = "cart", donation: int = 0, is_ticket: bool = True) -> Order:
        if status == "empty":
            return Order.objects.create(user=customer_user, name="cart")

        product_fixture = "donation" if donation > 0 else ("ticket" if is_ticket else "non_ticket")
        used_product = request.getfixturevalue(product_fixture + "_product")
        order = Order.objects.create(
            user=customer_user,
            name=used_product.name,
            name_ko=used_product.name_ko,
            name_en=used_product.name_en,
        )
        OrderProductRelation.objects.create(
            order=order, product=used_product, price=used_product.price, donation_price=donation
        )
        CustomerInfo.objects.create(order=order, name="홍길동", phone="01012345678", email="customer@example.com")

        if status == "cart":
            return order
        if status == "prepared":
            order.prepare_payment()
            return order

        # status >= 'completed' — OPR paid + PH completed.
        order.products.update(status=OrderProductRelation.OrderProductStatus.paid)
        PaymentHistory.objects.create(
            order=order,
            imp_id=_COMPLETED_ORDER_IMP_ID,
            status=PaymentHistoryStatus.completed,
            price=order.first_paid_price,
        )

        if status == "completed":
            return order

        # completed → refunded/partial_refunded 의 두 번째 PH 는 명시적으로 더 늦은 created_at 으로 강제.
        # auto_now_add 가 같은 microsecond 를 찍으면 current_status 의 `order_by("-created_at")` tie-break 가
        # 불안정 — freeze_time 테스트에서 더욱 그러함. 첫 PH 의 created_at + 1초 로 명시 update.
        first_ph = order.payment_histories.get()
        later_at = first_ph.created_at + timedelta(seconds=1)

        if status == "refunded":
            order.products.update(status=OrderProductRelation.OrderProductStatus.refunded)
            second_ph = PaymentHistory.objects.create(
                order=order, imp_id=_COMPLETED_ORDER_IMP_ID, status=PaymentHistoryStatus.refunded, price=0
            )
            PaymentHistory.objects.filter(id=second_ph.id).update(created_at=later_at)
            return order
        if status == "partial_refunded":
            second_ph = PaymentHistory.objects.create(
                order=order,
                imp_id=_COMPLETED_ORDER_IMP_ID,
                status=PaymentHistoryStatus.partial_refunded,
                price=order.first_paid_price // 2,
            )
            PaymentHistory.objects.filter(id=second_ph.id).update(created_at=later_at)
            return order
        raise ValueError(f"Unknown order_factory status: {status!r}")

    return make


@pytest.fixture
def ticket_opr(order_factory) -> OrderProductRelation:
    return order_factory(status="completed").products.get()


@pytest.fixture
def non_ticket_opr(order_factory) -> OrderProductRelation:
    return order_factory(status="completed", is_ticket=False).products.get()


@pytest.fixture
def used_ticket_opr(order_factory) -> OrderProductRelation:
    """status=used + is_ticket + category.event 연결된 OPR — 티켓 사용 완료(참가확인서 발급 가능) 상태."""
    order = order_factory(status="completed")
    order.products.update(status=OrderProductRelation.OrderProductStatus.used)
    opr = order.products.select_related("order__customer_info", "product__category").get()
    category = opr.product.category
    category.event = baker.make("event.Event", name="파이콘 한국 2026")
    category.save(update_fields=["event"])
    return opr


@pytest.fixture
def modifiable_option_relation(order_factory, ticket_product) -> OrderProductOptionRelation:
    """custom_response 수정 가능 옵션 — `response_modifiable_ends_at` 미래, paid OPR 에 attached."""
    completed_order = order_factory(status="completed")
    group = OptionGroup.objects.create(
        product=ticket_product,
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
    """`portone_client.find_payment_info` 를 mock. `.return_value` 미설정 시 호출 즉시 RuntimeError."""
    with _strict_portone_mock("find_payment_info") as mocked:
        yield mocked


@pytest.fixture
def mock_portone_req_cancel_payment():
    """`portone_client.req_cancel_payment` 를 mock — 환불 호출 검증 / 실패 주입에 사용.

    환불 호출은 반환값을 호출자가 사용하지 않으므로 (호출 인자/횟수만 검증), 명시 세팅 없이도 None 반환 허용.
    """
    with patch.object(portone_client, "req_cancel_payment") as mocked:
        mocked.return_value = None
        yield mocked


@pytest.fixture
def mock_portone_register():
    """`portone_client.register_or_update_prepared_payment` 를 mock — 결제 사전 등록 호출 검증.

    반환값을 호출자가 사용하지 않으므로 명시 세팅 없이도 None 반환 허용.
    """
    with patch.object(portone_client, "register_or_update_prepared_payment") as mocked:
        yield mocked


@pytest.fixture
def mock_portone_kcp_receipt():
    """`portone_client.get_kcp_receipt_search_data` 를 mock — `.return_value` 미설정 시 호출 즉시 RuntimeError.

    영수증 응답 dict 의 형태가 redirect 처리에 영향을 주므로 strict 모드.
    """
    with _strict_portone_mock("get_kcp_receipt_search_data") as mocked:
        yield mocked
