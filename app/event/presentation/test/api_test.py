import http
import uuid

import pytest
from django.urls import reverse
from event.presentation.test.conftest import PresentationTestEntity
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_presentation_api(api_client: APIClient, create_presentation_set: PresentationTestEntity):
    url = reverse("v1:presentation-list")
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) > 0


@pytest.mark.django_db
def test_presentation_category_filter_api(api_client: APIClient, create_presentation_set: PresentationTestEntity):
    url = f"{reverse('v1:presentation-list')}?categories={create_presentation_set.presentation_category.id}"
    response = api_client.get(url)

    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) > 0


@pytest.mark.django_db
def test_presentation_category_filter_api_should_not_return_unknown_category_id(
    api_client: APIClient, create_presentation_set: PresentationTestEntity
):
    url = f"{reverse('v1:presentation-list')}?categories={uuid.uuid4()}"
    response = api_client.get(url)

    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) == 0, "Should not return any presentations for unknown category ID"
