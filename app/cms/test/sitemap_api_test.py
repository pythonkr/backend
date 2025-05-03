import http

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_list_view(api_client, create_sitemap):
    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url)
    if response.status_code != http.HTTPStatus.OK:
        raise Exception("cms Sitemap list API raised error")


@pytest.mark.django_db
def test_retrieve_view(api_client, create_sitemap):
    url = reverse("v1:cms-sitemap-detail", kwargs={"pk": create_sitemap.id})
    response = api_client.get(url)
    if response.status_code != http.HTTPStatus.OK:
        raise Exception("cms Sitemap retrieve API raised error")
