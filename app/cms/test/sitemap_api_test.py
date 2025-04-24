import pytest
from django.urls import reverse

CMS_SITEMAP = "cms-sitemap"


@pytest.mark.django_db
def test_list_view(api_client, create_sitemap):
    url = reverse(CMS_SITEMAP)
    response = api_client.get(url)
    if response.status_code != 200:
        raise Exception("cms Sitemap list API raised error")


@pytest.mark.django_db
def test_retrieve_view(api_client, create_sitemap):
    url = reverse(CMS_SITEMAP)
    print("create_sitemap_id", create_sitemap.id)
    response = api_client.get(url, kwargs={"pk": create_sitemap.id})
    if response.status_code != 200:
        raise Exception("cms Sitemap retrieve API raised error")
