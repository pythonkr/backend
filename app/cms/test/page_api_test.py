import http

import pytest
from django.urls import reverse

PAGE_SITEMAP = "cms-page"


@pytest.mark.django_db
def test_list_view(api_client, create_page):
    url = reverse(PAGE_SITEMAP)
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.OK


@pytest.mark.django_db
def test_retrieve_view(api_client, create_page):
    url = reverse(PAGE_SITEMAP)
    response = api_client.get(url, kwargs={"pk": create_page.id})
    assert response.status_code == http.HTTPStatus.OK
