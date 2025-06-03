import http

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
    presentation_category = create_presentation_set.presentation_category
    url = reverse("v1:presentation-list") + f"?category={presentation_category.name}"
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK
    assert len(response.json()) > 0
