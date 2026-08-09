from datetime import UTC, datetime
from urllib.parse import urljoin

import pytest
from admin_api.test.helpers import OrderProductNotificationsAdminApi
from django.conf import settings
from notification.models.email import EmailNotificationHistory, EmailNotificationTemplate
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from shop.order.models import CustomerInfo, OrderProductRelation, TicketInfo


@pytest.fixture
def opr_email_template(superuser) -> EmailNotificationTemplate:
    return EmailNotificationTemplate.objects.create(
        code="ticket-qr",
        title="티켓 QR 안내",
        sent_from="from@example.com",
        data=(
            '{"title":"{{ product_name }} QR",'
            '"from_":"f",'
            '"send_to":"{{ participant_email }}",'
            '"body":"{{ participant_name }}님 {{ scancode_url }}"}'
        ),
        created_by=superuser,
        updated_by=superuser,
    )


@pytest.fixture
def two_ticket_order(order_factory, ticket_product):
    order = order_factory(status="completed")
    OrderProductRelation.objects.create(
        order=order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    return order


@pytest.mark.django_db
def test_opr_notification_preview_rejects_non_superuser(customer_client):
    response = OrderProductNotificationsAdminApi(http_client=customer_client).preview({})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_opr_notification_send_rejects_non_superuser(customer_client):
    response = OrderProductNotificationsAdminApi(http_client=customer_client).send({})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_opr_notification_preview_uses_product_scancode_url(api_client, opr_email_template, ticket_opr):
    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    order = ticket_opr.order
    assert recipient["dedupe_key"] == str(ticket_opr.id)
    assert recipient["context"]["scancode_url"] == urljoin(settings.BACKEND_DOMAIN, ticket_opr.scancode_path)
    assert recipient["context"]["order_name"] == order.name


@pytest.mark.django_db
def test_opr_notification_preview_fans_out_per_product(api_client, opr_email_template, two_ticket_order):
    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    recipients = response.json()["recipients"]
    assert len(recipients) == 2
    assert {r["recipient"] for r in recipients} == {"customer@example.com"}
    assert len({r["context"]["scancode_url"] for r in recipients}) == 2
    assert {r["dedupe_key"] for r in recipients} == {str(p.id) for p in two_ticket_order.products.all()}


@pytest.mark.django_db
def test_opr_notification_send_creates_one_sent_to_per_product(api_client, opr_email_template, two_ticket_order):
    response = OrderProductNotificationsAdminApi(http_client=api_client).send(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_201_CREATED
    history = EmailNotificationHistory.objects.get(id=response.json()["id"])
    sent_to_list = history.sent_to_list.all()
    assert len(sent_to_list) == 2
    assert {s.recipient for s in sent_to_list} == {"customer@example.com"}
    assert {s.dedupe_key for s in sent_to_list} == {str(p.id) for p in two_ticket_order.products.all()}


@pytest.mark.django_db
def test_opr_notification_preview_prefers_ticket_info_over_customer_info(api_client, opr_email_template, ticket_opr):
    TicketInfo.objects.create(
        order_product_relation=ticket_opr,
        name="참가자",
        phone="01099998888",
        email="participant@example.com",
        organization="파이콘",
        contribution_message="기여 메시지",
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["recipient"] == "participant@example.com"
    assert recipient["context"]["participant_name"] == "참가자"
    assert recipient["context"]["participant_organization"] == "파이콘"
    assert recipient["context"]["contribution_message"] == "기여 메시지"
    assert recipient["context"]["customer_email"] == "customer@example.com"


@pytest.mark.django_db
def test_opr_notification_preview_falls_back_to_customer_info(api_client, opr_email_template, ticket_opr):
    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["recipient"] == "customer@example.com"
    assert recipient["context"]["participant_name"] == "홍길동"


@pytest.mark.django_db
def test_opr_notification_preview_includes_refunded_product(api_client, opr_email_template, two_ticket_order):
    refunded = two_ticket_order.products.first()
    refunded.status = OrderProductRelation.OrderProductStatus.refunded
    refunded.save()

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    recipients = response.json()["recipients"]
    assert len(recipients) == 2
    assert str(refunded.id) in {r["dedupe_key"] for r in recipients}


@pytest.mark.django_db
def test_opr_notification_preview_includes_fully_refunded_order(api_client, opr_email_template, order_factory):
    order = order_factory(status="refunded")

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["dedupe_key"] == str(order.products.get().id)


@pytest.mark.django_db
def test_opr_notification_preview_excludes_unpaid_product(api_client, opr_email_template, order_factory):
    order_factory(status="cart")

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["recipients"] == []


@pytest.mark.django_db
def test_opr_notification_preview_product_id_filter_scopes_to_that_product(
    api_client, opr_email_template, order_factory, ticket_product, non_ticket_product
):
    order = order_factory(status="completed")
    OrderProductRelation.objects.create(
        order=order,
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)},
        params={"product_id": str(ticket_product.id)},
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["context"]["product_name"] == ticket_product.name


@pytest.mark.django_db
def test_opr_notification_preview_status_filter_scopes_to_opr_status(api_client, opr_email_template, two_ticket_order):
    used = two_ticket_order.products.first()
    used.status = OrderProductRelation.OrderProductStatus.used
    used.save()

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)},
        params={"status": "used"},
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["dedupe_key"] == str(used.id)


@pytest.mark.django_db
def test_opr_notification_preview_is_ticket_filter(api_client, opr_email_template, order_factory, non_ticket_product):
    order = order_factory(status="completed")
    goods = OrderProductRelation.objects.create(
        order=order,
        product=non_ticket_product,
        price=non_ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)},
        params={"is_ticket": "true"},
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["dedupe_key"] != str(goods.id)


@pytest.mark.django_db
def test_opr_notification_send_rejects_when_no_eligible_recipients(api_client, opr_email_template, ticket_opr):
    CustomerInfo.objects.filter(order=ticket_opr.order).hard_delete()

    response = OrderProductNotificationsAdminApi(http_client=api_client).send(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "발송 대상이 없습니다" in str(response.json())


@pytest.mark.django_db
def test_opr_notification_context_override_wins(api_client, opr_email_template, ticket_opr):
    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {
            "channel": "email",
            "template_id": str(opr_email_template.id),
            "context_override": {"participant_name": "덮어쓴 이름"},
        }
    )

    assert response.status_code == HTTP_200_OK
    [recipient] = response.json()["recipients"]
    assert recipient["context"]["participant_name"] == "덮어쓴 이름"


@pytest.mark.django_db
def test_opr_notification_preview_query_count_does_not_grow_with_targets(
    api_client, opr_email_template, order_factory, ticket_product, django_assert_max_num_queries
):
    for _ in range(5):
        order = order_factory(status="completed")
        OrderProductRelation.objects.create(
            order=order,
            product=ticket_product,
            price=ticket_product.price,
            status=OrderProductRelation.OrderProductStatus.paid,
        )

    with django_assert_max_num_queries(12):
        response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
            {"channel": "email", "template_id": str(opr_email_template.id)}
        )

    assert response.status_code == HTTP_200_OK
    assert len(response.json()["recipients"]) == 10


@pytest.mark.django_db
def test_opr_notification_preview_provides_korean_aliases(api_client, opr_email_template, ticket_opr):
    TicketInfo.objects.create(
        order_product_relation=ticket_opr,
        name="참가자",
        phone="01099998888",
        email="participant@example.com",
        organization="파이콘",
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    ctx = response.json()["recipients"][0]["context"]
    assert ctx["성함"] == ctx["성명"] == "참가자"
    assert ctx["소속"] == "파이콘"
    assert "연도" not in ctx


@pytest.mark.django_db
def test_opr_notification_preview_derives_year_from_event(api_client, opr_email_template, used_ticket_opr):
    event = used_ticket_opr.product.category.event
    event.event_start_at = datetime(2026, 8, 15, tzinfo=UTC)
    event.save(update_fields=["event_start_at"])

    response = OrderProductNotificationsAdminApi(http_client=api_client).preview(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["recipients"][0]["context"]["연도"] == 2026


@pytest.mark.django_db
def test_opr_notification_render_returns_html_for_first_target(api_client, opr_email_template, ticket_opr):
    TicketInfo.objects.create(
        order_product_relation=ticket_opr,
        name="참가자",
        phone="01099998888",
        email="participant@example.com",
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).render(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert "참가자님" in body
    assert urljoin(settings.BACKEND_DOMAIN, ticket_opr.scancode_path) in body


@pytest.mark.django_db
def test_opr_notification_render_scopes_to_filtered_target(api_client, opr_email_template, two_ticket_order):
    second = two_ticket_order.products.last()

    response = OrderProductNotificationsAdminApi(http_client=api_client).render(
        {"channel": "email", "template_id": str(opr_email_template.id)},
        params={"id": str(second.id)},
    )

    assert response.status_code == HTTP_200_OK
    assert urljoin(settings.BACKEND_DOMAIN, second.scancode_path) in response.content.decode()


@pytest.mark.django_db
def test_opr_notification_render_rejects_when_no_target(api_client, opr_email_template, ticket_opr):
    CustomerInfo.objects.filter(order=ticket_opr.order).hard_delete()

    response = OrderProductNotificationsAdminApi(http_client=api_client).render(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_opr_notification_render_rejects_non_superuser(customer_client):
    response = OrderProductNotificationsAdminApi(http_client=customer_client).render({})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_opr_notification_render_escapes_participant_supplied_html(api_client, opr_email_template, ticket_opr):
    # 참가자 정보는 구매자가 자유 입력하므로, 렌더 결과가 admin 브라우저에서 실행되면 stored XSS 가 된다.
    payload = '<img src=x onerror="alert(1)">'
    TicketInfo.objects.create(
        order_product_relation=ticket_opr,
        name=payload,
        phone="01099998888",
        email="participant@example.com",
    )

    response = OrderProductNotificationsAdminApi(http_client=api_client).render(
        {"channel": "email", "template_id": str(opr_email_template.id)}
    )

    assert response.status_code == HTTP_200_OK
    body = response.content.decode()
    assert payload not in body
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in body
