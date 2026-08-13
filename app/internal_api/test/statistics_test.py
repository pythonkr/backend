from datetime import timedelta

import pytest
from core.util.dateutil import now_aware
from django.urls import reverse
from internal_api.models import RegistrationDeskConfig
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN
from shop.order.models import OrderProductRelation

STATISTICS_URL = reverse("v1:registration_desk:desk-statistics")


@pytest.mark.django_db
def test_statistics_rejects_anonymous(anon_client):
    assert anon_client.get(STATISTICS_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_statistics_rejects_non_superuser(customer_client):
    assert customer_client.get(STATISTICS_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_statistics_rejects_when_no_config_applies_today(staff_client, order_factory, ticket_config):
    order_factory(status="completed")
    ticket_config.start_date = ticket_config.end_date = now_aware().date() + timedelta(days=1)
    ticket_config.save()

    response = staff_client.get(STATISTICS_URL)

    assert response.status_code == HTTP_403_FORBIDDEN
    assert "등록 데스크 설정" in str(response.json())


@pytest.mark.django_db
def test_statistics_counts_used_as_registered_and_paid_as_waiting(staff_client, order_factory, ticket_config, used_opr):
    order_factory(status="completed")  # paid → 대기
    order_factory(status="refunded")  # 환불 → 집계 제외

    response = staff_client.get(STATISTICS_URL)

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "registration_target_count": 2,
        "registered_count": 1,
        "waiting_count": 1,
    }


@pytest.mark.django_db
def test_statistics_excludes_pending_cart_products(staff_client, order_factory, ticket_config):
    order_factory(status="cart")

    response = staff_client.get(STATISTICS_URL)

    assert response.json() == {"registration_target_count": 0, "registered_count": 0, "waiting_count": 0}


@pytest.mark.django_db
def test_statistics_counts_only_config_categories(staff_client, order_factory, ticket_config):
    order_factory(status="completed")
    order_factory(status="completed", is_ticket=False)  # 설정(티켓 카테고리) 밖

    response = staff_client.get(STATISTICS_URL)

    assert response.json() == {"registration_target_count": 1, "registered_count": 0, "waiting_count": 1}


@pytest.mark.django_db
def test_statistics_counts_nothing_when_config_has_no_categories(staff_client, order_factory, desk_event):
    # 빈 카테고리를 "전체" 로 해석하지 않는다 — 설정 실수의 영향을 줄이기 위한 의도적 동작.
    RegistrationDeskConfig.objects.create(name="빈 설정", event=desk_event)
    order_factory(status="completed")

    response = staff_client.get(STATISTICS_URL)

    assert response.json() == {"registration_target_count": 0, "registered_count": 0, "waiting_count": 0}


@pytest.mark.django_db
def test_statistics_excludes_non_ticket_category(staff_client, order_factory, non_ticket_product, desk_event):
    config = RegistrationDeskConfig.objects.create(name="굿즈", event=desk_event)
    config.categories.add(non_ticket_product.category)
    order_factory(status="completed", is_ticket=False)

    assert staff_client.get(STATISTICS_URL).json()["registration_target_count"] == 0


@pytest.mark.django_db
def test_statistics_uses_config_matching_today(staff_client, order_factory, ticket_config, ticket_product, desk_event):
    order_factory(status="completed")
    yesterday = now_aware().date() - timedelta(days=1)
    ticket_config.start_date = ticket_config.end_date = yesterday
    ticket_config.save()
    # 어제 설정은 티켓을 담고 있지만, 오늘 설정은 비어 있어 아무것도 집계되지 않아야 한다.
    RegistrationDeskConfig.objects.create(
        name="오늘", event=desk_event, start_date=now_aware().date(), end_date=now_aware().date()
    )

    response = staff_client.get(STATISTICS_URL)

    assert response.json() == {"registration_target_count": 0, "registered_count": 0, "waiting_count": 0}


@pytest.mark.django_db
def test_statistics_ignores_soft_deleted_order_products(staff_client, order_factory, ticket_config):
    order = order_factory(status="completed")
    OrderProductRelation.objects.filter(order=order).delete()

    response = staff_client.get(STATISTICS_URL)

    assert response.json() == {"registration_target_count": 0, "registered_count": 0, "waiting_count": 0}


@pytest.mark.django_db
def test_statistics_ignores_soft_deleted_config_categories(staff_client, order_factory, ticket_config, ticket_product):
    order_factory(status="completed")
    ticket_product.category.delete()

    response = staff_client.get(STATISTICS_URL)

    assert response.json()["registration_target_count"] == 0
