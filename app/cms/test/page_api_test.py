import http

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_list_view(api_client, create_page):
    url = reverse("v1:cms-page-list")
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK


@pytest.mark.django_db
def test_retrieve_view(api_client, create_page):
    url = reverse("v1:cms-page-detail", kwargs={"pk": create_page.id})
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK
