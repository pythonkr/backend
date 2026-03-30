import http
from datetime import datetime

import pytest
from django.urls import reverse
from event.models import Event
from event.sponsor.models import Sponsor, SponsorTier, SponsorTierSponsorRelation
from file.models import PublicFile
from rest_framework.test import APIClient
from user.models.organization import Organization


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def two_events():
    organization = Organization.objects.create(name="Test Organization")
    old_event = Event.objects.create(
        organization=organization, name="PyCon Korea 2025", event_start_at=datetime(2025, 8, 1)
    )
    new_event = Event.objects.create(
        organization=organization, name="PyCon Korea 2026", event_start_at=datetime(2026, 8, 1)
    )
    return old_event, new_event


def _make_sponsor(event, name, tier):
    logo = PublicFile.objects.create(
        file=f"public/{name}.png",
        mimetype="image/png",
        hash=name,
        size=0,
    )
    sponsor = Sponsor.objects.create(event=event, name=name, logo=logo)
    SponsorTierSponsorRelation.objects.create(tier=tier, sponsor=sponsor)
    return sponsor


@pytest.mark.django_db
def test_sponsor_defaults_to_latest_event(api_client: APIClient, two_events):
    old_event, new_event = two_events

    # Given: 각 행사에 후원 등급과 후원사가 있음
    old_tier = SponsorTier.objects.create(event=old_event, name="Gold", order=0)
    new_tier = SponsorTier.objects.create(event=new_event, name="Gold", order=0)

    _make_sponsor(old_event, "Old Sponsor", old_tier)
    _make_sponsor(new_event, "New Sponsor", new_tier)

    # When: event 파라미터 없이 요청
    response = api_client.get(reverse("v1:sponsor-list"))

    # Then: 최신 행사(2026)의 후원 등급만 반환
    assert response.status_code == http.HTTPStatus.OK
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["id"] == str(new_tier.id)


@pytest.mark.django_db
def test_sponsor_filter_by_event_name(api_client: APIClient, two_events):
    old_event, new_event = two_events

    old_tier = SponsorTier.objects.create(event=old_event, name="Gold", order=0)
    new_tier = SponsorTier.objects.create(event=new_event, name="Gold", order=0)

    _make_sponsor(old_event, "Old Sponsor", old_tier)
    _make_sponsor(new_event, "New Sponsor", new_tier)

    # When: 2025 행사를 명시적으로 지정
    response = api_client.get(reverse("v1:sponsor-list"), {"event": "PyCon Korea 2025"})

    # Then: 2025 행사의 후원 등급만 반환
    assert response.status_code == http.HTTPStatus.OK
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["id"] == str(old_tier.id)


@pytest.mark.django_db
def test_sponsor_no_events_returns_empty(api_client: APIClient):
    # When: 이벤트가 없을 때 요청
    response = api_client.get(reverse("v1:sponsor-list"))

    # Then: 빈 응답
    assert response.status_code == http.HTTPStatus.OK
    assert response.json() == []
