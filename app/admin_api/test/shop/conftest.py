import pytest
from notification.models import EmailNotificationTemplate
from shop.conftest import (  # noqa: F401
    anon_client,
    completed_order,
    customer_client,
    donation_completed_order,
    donation_product,
    donation_refunded_order,
    empty_cart,
    mock_portone_find_payment_info,
    mock_portone_kcp_receipt,
    mock_portone_register,
    mock_portone_req_cancel_payment,
    mocked_on_commit,
    modifiable_option_relation,
    option,
    option_group,
    other_client,
    other_user,
    partial_refunded_order,
    pending_order,
    product,
    products_by_status,
    refunded_order,
    single_product_cart,
    staff_client,
    staff_user,
    tag,
)


@pytest.fixture
def order_email_template(superuser) -> EmailNotificationTemplate:
    # `send_payment_completed_notifications` Celery task 와 동일한 Order-derived 변수만 사용 —
    # admin send/preview API 도 동일한 변수를 자동 노출하므로 context_override 없이 발송 가능.
    return EmailNotificationTemplate.objects.create(
        code="order-payment-completed",
        title="결제 완료",
        sent_from="from@example.com",
        data=(
            '{"title":"{{ order_name }} 결제 완료",'
            '"from_":"f",'
            '"send_to":"{{ customer_email }}",'
            '"body":"{{ customer_name }}님 {{ first_paid_price }}원 결제 완료"}'
        ),
        created_by=superuser,
        updated_by=superuser,
    )
