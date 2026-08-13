import pytest
from event.models import Event
from internal_api.models import RegistrationDeskConfig
from model_bakery import baker
from shop.conftest import (  # noqa: F401
    anon_client,
    customer_client,
    customer_user,
    donation_product,
    mock_portone_req_cancel_payment,
    modifiable_option_relation,
    non_ticket_product,
    option,
    option_group,
    order_factory,
    staff_client,
    staff_user,
    tag,
    ticket_product,
)
from shop.order.models import OrderProductRelation


@pytest.fixture
def used_opr(order_factory):  # noqa: F811
    """체크인(사용) 완료된 티켓 OPR."""
    order = order_factory(status="completed")
    order.products.update(status=OrderProductRelation.OrderProductStatus.used)
    return order.products.get()


@pytest.fixture
def desk_event(db) -> Event:
    return baker.make("event.Event", name="파이콘 한국 2026", event_start_at="2026-08-01T00:00:00Z")


@pytest.fixture
def ticket_config(ticket_product, desk_event) -> RegistrationDeskConfig:  # noqa: F811
    """`ticket_product` 의 카테고리만 집계하는, 기간 제한 없는 데스크 설정."""
    config = RegistrationDeskConfig.objects.create(name="티켓", event=desk_event)
    config.categories.add(ticket_product.category)
    return config
