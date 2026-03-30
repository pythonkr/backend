import http
import urllib.parse
from datetime import datetime

import pytest
from django.urls import reverse
from event.models import Event
from event.presentation.models import Presentation, PresentationType
from event.presentation.test.conftest import PresentationTestEntity
from rest_framework.test import APIClient
from user.models.organization import Organization


@pytest.mark.django_db
def test_presentation_api(api_client: APIClient, create_presentation_set: PresentationTestEntity):
    url = reverse("v1:presentation-list")
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) > 0


@pytest.mark.django_db
def test_presentation_event_type_filter_api(api_client: APIClient):
    # Given: 행사 2개에 각각 2 종류의 발표 유형이 있고, 각 발표 유형마다 1개의 발표가 있음.
    organization = Organization.objects.create(name="Test Organization")
    event_1: Event = Event.objects.create(
        organization=organization, name="Test Event 1", event_start_at=datetime(2025, 8, 1)
    )
    event_2: Event = Event.objects.create(
        organization=organization, name="Test Event 2", event_start_at=datetime(2026, 8, 1)
    )

    event_1_prst_type_1 = PresentationType.objects.create(event=event_1, name="Type 1")
    event_1_prst_type_2 = PresentationType.objects.create(event=event_1, name="Type 2")
    PresentationType.objects.create(event=event_2, name="Type 1")
    PresentationType.objects.create(event=event_2, name="Type 2")

    event_1_prst_type_1_prst = Presentation.objects.create(type=event_1_prst_type_1, title="Presentation 1")
    event_1_prst_type_2_prst = Presentation.objects.create(type=event_1_prst_type_2, title="Presentation 2")

    # When: API 요청을 통해 행사 1의 발표 유형 1과 2에 해당하는 발표를 요청할 시
    qs = urllib.parse.urlencode(
        {"event": event_1.name, "types": f"{event_1_prst_type_1.name},{event_1_prst_type_2.name}"}
    )
    response = api_client.get(f"{reverse('v1:presentation-list')}?{qs}")

    # Then: 행사 1의 발표 유형 1과 2에 해당하는 발표가 반환되어야 함.
    assert response.status_code == http.HTTPStatus.OK

    response_data = response.json()
    assert len(response_data) == 2, "Should return 2 presentations for event 1 with specified types"
    assert {datum["id"] for datum in response_data} == {
        str(event_1_prst_type_1_prst.id),
        str(event_1_prst_type_2_prst.id),
    }


@pytest.mark.django_db
def test_presentation_defaults_to_latest_event(api_client: APIClient):
    # Given: 2개의 행사가 있고, 각각 발표가 있음.
    organization = Organization.objects.create(name="Test Organization")
    old_event = Event.objects.create(
        organization=organization, name="PyCon Korea 2025", event_start_at=datetime(2025, 8, 1)
    )
    new_event = Event.objects.create(
        organization=organization, name="PyCon Korea 2026", event_start_at=datetime(2026, 8, 1)
    )

    old_type = PresentationType.objects.create(event=old_event, name="Talk")
    new_type = PresentationType.objects.create(event=new_event, name="Talk")

    Presentation.objects.create(type=old_type, title="Old Presentation")
    new_prst = Presentation.objects.create(type=new_type, title="New Presentation")

    # When: event 파라미터 없이 요청
    response = api_client.get(reverse("v1:presentation-list"))

    # Then: 최신 행사(2026)의 발표만 반환
    assert response.status_code == http.HTTPStatus.OK
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["id"] == str(new_prst.id)
