from datetime import datetime

import pytest
from django.urls import reverse
from event.models import Event
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN
from shop.product.models import Category, CategoryGroup
from user.models.organization import Organization

LIST_URL = reverse("v1:admin-shop-category-list")
SELECTABLES_URL = LIST_URL + "selectables/"


@pytest.fixture
def category_fixtures():
    org = Organization.objects.create(name="Org")
    event = Event.objects.create(organization=org, name="PyCon Korea 2026", event_start_at=datetime(2026, 8, 1))
    g2025 = CategoryGroup.objects.create(name="2025")
    g2026 = CategoryGroup.objects.create(name="2026")
    ticket = Category.objects.create(group=g2026, name="Conference", is_ticket=True, event=event)
    goods = Category.objects.create(group=g2025, name="T-Shirt", is_ticket=False)
    return {"event": event, "g2025": g2025, "g2026": g2026, "ticket": ticket, "goods": goods}


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_category_list_rejects_non_superuser(request, client_fixture):
    response = request.getfixturevalue(client_fixture).get(LIST_URL)
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_category_list_returns_categories(api_client, category_fixtures):
    response = api_client.get(LIST_URL)
    assert response.status_code == HTTP_200_OK
    rows = response.json()["results"] if isinstance(response.json(), dict) else response.json()
    by_name = {r["name"]: r for r in rows}
    assert {"Conference", "T-Shirt"} <= set(by_name)
    assert by_name["Conference"]["is_ticket"] is True
    assert by_name["Conference"]["group"] == str(category_fixtures["g2026"].id)
    assert by_name["Conference"]["event"] == str(category_fixtures["event"].id)


@pytest.mark.django_db
def test_category_selectables_include_meta(api_client, category_fixtures):
    # selectables 결과의 각 category 는 Category.get_choice_meta() 로 group/is_ticket/event 메타를 실어야 한다.
    response = api_client.get(SELECTABLES_URL)
    assert response.status_code == HTTP_200_OK
    body = response.json()
    ticket_meta = {c["const"]: c for c in body["results"]}[str(category_fixtures["ticket"].id)]["meta"]
    assert ticket_meta["group"] == "2026"
    assert ticket_meta["is_ticket"] is True
    assert ticket_meta["event"] == str(category_fixtures["event"])
    # meta_schema 는 모델의 choices_meta_schema 를 반영한다.
    assert {"is_ticket", "group", "event"} <= set(body["meta_schema"])


@pytest.mark.django_db
def test_category_selectables_include_audit_meta(api_client, category_fixtures):
    # BaseAbstractModel 의 audit 메타(created_by/updated_by/created_at/updated_at)가 자동으로 붙어야 한다.
    response = api_client.get(SELECTABLES_URL)
    assert response.status_code == HTTP_200_OK
    ticket_meta = {c["const"]: c for c in response.json()["results"]}[str(category_fixtures["ticket"].id)]["meta"]
    assert {"created_by", "updated_by", "created_at", "updated_at"} <= set(ticket_meta)
    assert ticket_meta["created_at"] is not None


@pytest.mark.django_db
def test_category_filter_by_group(api_client, category_fixtures):
    response = api_client.get(LIST_URL, {"group": str(category_fixtures["g2026"].id)})
    rows = response.json()["results"] if isinstance(response.json(), dict) else response.json()
    assert {r["name"] for r in rows} == {"Conference"}


@pytest.mark.django_db
def test_category_filter_by_is_ticket(api_client, category_fixtures):
    response = api_client.get(LIST_URL, {"is_ticket": "true"})
    rows = response.json()["results"] if isinstance(response.json(), dict) else response.json()
    assert {r["name"] for r in rows} == {"Conference"}
