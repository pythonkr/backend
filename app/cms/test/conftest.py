import pytest
from cms.models import Page, Sitemap
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_page():
    page = Page.objects.create(
        title="제목",
        subtitle="부제목",
    )
    return page


@pytest.fixture
def create_sitemap(create_page):
    sitemap = Sitemap.objects.create(page=create_page)
    return sitemap
