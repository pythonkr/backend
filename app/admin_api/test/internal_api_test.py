from datetime import date

import pytest
from django.db.utils import IntegrityError
from django.urls import reverse
from event.models import Event
from file.models import PublicFile
from internal_api.models import RegistrationDeskConfig
from model_bakery import baker
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)
from rest_framework.test import APIClient
from shop.conftest import ticket_product  # noqa: F401

LIST_URL = reverse("v1:admin-registration-desk-config-list")


def _detail_url(pk) -> str:
    return reverse("v1:admin-registration-desk-config-detail", args=[pk])


def _payload(event, category_id, **overrides) -> dict:
    return {"name": "설정", "event": str(event.id), "categories": [str(category_id)], **overrides}


@pytest.fixture
def anon_client() -> APIClient:
    return APIClient()


@pytest.fixture
def customer_client(customer_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=customer_user)
    return client


@pytest.fixture
def event(db) -> Event:
    return baker.make("event.Event", name="파이콘 한국 2026")


@pytest.fixture
def day1_config(event) -> RegistrationDeskConfig:
    return RegistrationDeskConfig.objects.create(
        name="Day 1", event=event, start_date=date(2026, 8, 15), end_date=date(2026, 8, 15)
    )


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_config_list_rejects_non_superuser(request, client_fixture):
    assert request.getfixturevalue(client_fixture).get(LIST_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_config_list_is_paginated(api_client, day1_config):
    response = api_client.get(LIST_URL)

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["name"] == "Day 1"


@pytest.mark.django_db
def test_config_create_persists_target_categories(api_client, ticket_product, event):  # noqa: F811
    response = api_client.post(
        LIST_URL,
        {
            "name": "Day 1",
            "event": str(event.id),
            "start_date": "2026-08-15",
            "end_date": "2026-08-15",
            "categories": [str(ticket_product.category_id)],
        },
        format="json",
    )

    assert response.status_code == HTTP_201_CREATED
    body = response.json()
    assert body["categories"] == [str(ticket_product.category_id)]
    config = RegistrationDeskConfig.objects.get(id=body["id"])
    assert config.start_date == date(2026, 8, 15)
    assert list(config.categories.all()) == [ticket_product.category]


@pytest.mark.django_db
def test_config_exposes_event_logo_url(api_client, event, ticket_product):  # noqa: F811
    logo = PublicFile.objects.create(file="public/desk-logo.png", mimetype="image/png", hash="desk-logo", size=0)
    event.logo = logo
    event.save()

    response = api_client.post(LIST_URL, _payload(event, ticket_product.category_id), format="json")

    assert response.status_code == HTTP_201_CREATED
    assert response.json()["logo_url"] == logo.file.url


@pytest.mark.django_db
def test_config_create_requires_event(api_client):
    response = api_client.post(LIST_URL, {"name": "이벤트 없음"}, format="json")

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "event" in str(response.json())


@pytest.mark.django_db
def test_config_create_rejects_end_date_before_start_date(api_client, event, ticket_product):  # noqa: F811
    response = api_client.post(
        LIST_URL,
        _payload(event, ticket_product.category_id, start_date="2026-08-16", end_date="2026-08-15"),
        format="json",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "end_date" in str(response.json())


@pytest.mark.django_db
def test_config_create_rejects_overlapping_period(api_client, day1_config, event, ticket_product):  # noqa: F811
    response = api_client.post(
        LIST_URL,
        _payload(event, ticket_product.category_id, start_date="2026-08-15", end_date="2026-08-16"),
        format="json",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "Day 1" in str(response.json())


@pytest.mark.django_db
def test_config_create_allows_adjacent_period(api_client, day1_config, event, ticket_product):  # noqa: F811
    response = api_client.post(
        LIST_URL,
        _payload(event, ticket_product.category_id, start_date="2026-08-16", end_date="2026-08-16"),
        format="json",
    )

    assert response.status_code == HTTP_201_CREATED


@pytest.mark.django_db
def test_config_create_rejects_open_ended_period_when_another_exists(
    api_client,
    day1_config,
    event,
    ticket_product,  # noqa: F811
):
    response = api_client.post(LIST_URL, _payload(event, ticket_product.category_id), format="json")

    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_config_update_does_not_conflict_with_itself(api_client, day1_config):
    response = api_client.patch(_detail_url(day1_config.id), {"name": "첫째 날"}, format="json")

    assert response.status_code == HTTP_200_OK
    assert response.json()["name"] == "첫째 날"


@pytest.mark.django_db
def test_config_partial_update_merges_stored_dates_for_overlap_check(api_client, day1_config, event):
    RegistrationDeskConfig.objects.create(
        name="Day 2", event=event, start_date=date(2026, 8, 16), end_date=date(2026, 8, 16)
    )

    # end_date 만 보내도 저장된 start_date 와 합쳐 Day 2 와의 겹침을 잡아야 한다.
    response = api_client.patch(_detail_url(day1_config.id), {"end_date": "2026-08-16"}, format="json")

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "Day 2" in str(response.json())


@pytest.mark.django_db
def test_config_destroy_soft_deletes(api_client, day1_config):
    assert api_client.delete(_detail_url(day1_config.id)).status_code == HTTP_204_NO_CONTENT

    day1_config.refresh_from_db()
    assert day1_config.deleted_at is not None
    assert api_client.get(LIST_URL).json()["count"] == 0


@pytest.mark.django_db
def test_config_json_schema_and_selectables_are_available(api_client, day1_config):
    schema_response = api_client.get(f"{LIST_URL}json-schema/")
    selectables_response = api_client.get(f"{LIST_URL}selectables/")

    assert schema_response.status_code == HTTP_200_OK
    assert "start_date" in schema_response.json()["schema"]["properties"]
    assert selectables_response.status_code == HTTP_200_OK
    assert [row["const"] for row in selectables_response.json()["results"]] == [str(day1_config.id)]


@pytest.mark.django_db
def test_config_create_rejects_empty_categories(api_client, event):
    response = api_client.post(LIST_URL, {"name": "빈 설정", "event": str(event.id), "categories": []}, format="json")

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "categories" in str(response.json())


@pytest.mark.django_db
def test_config_create_rejects_category_of_other_event(api_client, event, ticket_product):  # noqa: F811
    other_event = baker.make("event.Event", name="다른 행사")
    ticket_product.category.event = other_event
    ticket_product.category.save(update_fields=["event"])

    response = api_client.post(LIST_URL, _payload(event, ticket_product.category_id), format="json")

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "categories" in str(response.json())


@pytest.mark.django_db
def test_config_create_allows_category_without_event(api_client, event, ticket_product):  # noqa: F811
    assert ticket_product.category.event_id is None

    response = api_client.post(LIST_URL, _payload(event, ticket_product.category_id), format="json")

    assert response.status_code == HTTP_201_CREATED


@pytest.mark.django_db
def test_config_overlapping_period_is_blocked_by_db_constraint(event):
    # 시리얼라이저를 우회한 동시 요청까지 DB EXCLUDE 제약이 막는다.
    RegistrationDeskConfig.objects.create(
        name="Day 1", event=event, start_date=date(2026, 8, 15), end_date=date(2026, 8, 16)
    )

    with pytest.raises(IntegrityError):
        RegistrationDeskConfig.objects.create(
            name="겹침", event=event, start_date=date(2026, 8, 16), end_date=date(2026, 8, 17)
        )


@pytest.mark.django_db
def test_config_overlapping_period_ignores_soft_deleted(event):
    RegistrationDeskConfig.objects.create(
        name="Day 1", event=event, start_date=date(2026, 8, 15), end_date=date(2026, 8, 16)
    ).delete()

    RegistrationDeskConfig.objects.create(
        name="Day 1 재등록", event=event, start_date=date(2026, 8, 15), end_date=date(2026, 8, 16)
    )
