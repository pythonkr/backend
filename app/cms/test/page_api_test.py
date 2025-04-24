import pytest
from django.urls import reverse

PAGE_SITEMAP = "cms-page"


@pytest.mark.django_db
def test_list_view(api_client, create_page):
    url = reverse(PAGE_SITEMAP)
    response = api_client.get(url)
    if response.status_code != 200:
        raise Exception("cms Page list API raised error")


@pytest.mark.django_db
def test_retrieve_view(api_client, create_page):
    url = reverse(PAGE_SITEMAP)
    response = api_client.get(url, kwargs={"pk": create_page.id})
    if response.status_code != 200:
        raise Exception("cms Page retrieve API raised error")
