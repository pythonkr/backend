from datetime import timedelta

import pytest
from core.util.dateutil import now_aware
from django.urls import reverse
from file.models import PublicFile
from model_bakery import baker
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN
from shop.order.models import OrderProductRelationTag

CONFIGURATION_URL = reverse("v1:registration_desk:desk-configuration")


@pytest.mark.django_db
def test_configuration_rejects_anonymous(anon_client):
    assert anon_client.get(CONFIGURATION_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_configuration_rejects_non_superuser(customer_client):
    assert customer_client.get(CONFIGURATION_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_configuration_returns_config_of_today(staff_client, ticket_config, desk_event):
    response = staff_client.get(CONFIGURATION_URL)

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert set(body) == {"id", "name", "start_date", "end_date", "event", "available_tags"}
    assert body["id"] == str(ticket_config.id)
    assert body["name"] == "티켓"
    assert (body["start_date"], body["end_date"]) == ("0001-01-01", "9999-12-31")
    assert set(body["event"]) == {"id", "name", "event_start_at", "event_end_at", "logo_url"}
    assert body["event"]["id"] == str(desk_event.id)
    assert body["event"]["logo_url"] is None
    assert body["available_tags"] == []


@pytest.mark.django_db
def test_configuration_rejects_when_no_config_applies_today(staff_client, ticket_config):
    ticket_config.start_date = ticket_config.end_date = now_aware().date() + timedelta(days=1)
    ticket_config.save()

    response = staff_client.get(CONFIGURATION_URL)

    assert response.status_code == HTTP_403_FORBIDDEN
    assert "등록 데스크 설정" in str(response.json())


@pytest.mark.django_db
def test_configuration_exposes_event_logo(staff_client, ticket_config, desk_event):
    desk_event.logo = PublicFile.objects.create(
        file="public/desk-logo.png", mimetype="image/png", hash="desk-logo", size=0
    )
    desk_event.save()

    assert staff_client.get(CONFIGURATION_URL).json()["event"]["logo_url"] == desk_event.logo.file.url


@pytest.mark.django_db
def test_configuration_uses_event_of_current_desk_config(staff_client, ticket_config):
    config_event = baker.make("event.Event", name="2025", event_start_at="2025-08-01T00:00:00Z")
    baker.make("event.Event", name="2027", event_start_at="2027-08-01T00:00:00Z")
    ticket_config.event = config_event
    ticket_config.save()

    assert staff_client.get(CONFIGURATION_URL).json()["event"]["id"] == str(config_event.id)


@pytest.mark.django_db
def test_configuration_lists_available_tags(staff_client, ticket_config):
    OrderProductRelationTag.objects.create(code="volunteer", name="자원봉사자", priority=2)
    OrderProductRelationTag.objects.create(code="speaker", name="발표자", priority=1)
    OrderProductRelationTag.objects.create(code="deleted", name="삭제됨").delete()

    tags = staff_client.get(CONFIGURATION_URL).json()["available_tags"]

    # 소프트 삭제 태그는 빠지고, priority 순서로 고정된다.
    assert [tag["code"] for tag in tags] == ["speaker", "volunteer"]
