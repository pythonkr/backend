import http
from datetime import datetime

import pytest
from django.urls import reverse
from event.models import Event
from rest_framework.test import APIClient
from user.models.organization import Organization


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def two_events():
    org = Organization.objects.create(name="Test Organization")
    old = Event.objects.create(
        organization=org,
        name="PyCon Korea 2025",
        name_en="PyCon Korea 2025 (EN)",
        event_start_at=datetime(2025, 8, 1),
    )
    new = Event.objects.create(
        organization=org,
        name="PyCon Korea 2026",
        name_en="PyCon Korea 2026 (EN)",
        event_start_at=datetime(2026, 8, 1),
    )
    return old, new


@pytest.mark.django_db
def test_event_list_returns_active_events_latest_first(api_client: APIClient, two_events):
    old, new = two_events

    response = api_client.get(reverse("v1:event-list"))

    assert response.status_code == http.HTTPStatus.OK
    data = response.json()
    assert [e["id"] for e in data] == [str(new.id), str(old.id)]  # Meta ordering: 최신 우선
    assert set(data[0]) == {"id", "name", "slogan", "description", "event_start_at", "event_end_at"}


@pytest.mark.django_db
def test_event_list_empty_when_no_events(api_client: APIClient):
    assert api_client.get(reverse("v1:event-list")).json() == []


@pytest.mark.django_db
def test_event_list_returns_english_with_accept_language(api_client: APIClient, two_events):
    response = api_client.get(reverse("v1:event-list"), headers={"accept-language": "en"})

    assert response.status_code == http.HTTPStatus.OK
    assert response.json()[0]["name"] == "PyCon Korea 2026 (EN)"
