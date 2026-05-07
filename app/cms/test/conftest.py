import pytest
from cms.models import DomainGroup, Page, Sitemap
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_page():
    return Page.objects.create(title="제목", subtitle="부제목")


@pytest.fixture
def create_domain_group():
    return DomainGroup.objects.create(name="테스트 그룹", domains=["test.pycon.kr"])


@pytest.fixture
def create_sitemap(create_page, create_domain_group):
    return Sitemap.objects.create(page=create_page, domain_group=create_domain_group)
