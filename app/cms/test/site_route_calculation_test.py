import pytest
from cms.models import Page, Sitemap


@pytest.mark.django_db
def test_route_calculation():
    # Create a root sitemap
    root_sitemap = Sitemap.objects.create(
        route_code="root",
        name="Root Sitemap",
        page=Page.objects.create(title="Root Page", subtitle="Root Subtitle"),
    )

    # Create a child sitemap
    child_sitemap = Sitemap.objects.create(
        route_code="child",
        name="Child Sitemap",
        parent_sitemap=root_sitemap,
        page=Page.objects.create(title="Child Page", subtitle="Child Subtitle"),
    )

    # Create a grandchild sitemap
    grandchild_sitemap = Sitemap.objects.create(
        route_code="grandchild",
        name="Grandchild Sitemap",
        parent_sitemap=child_sitemap,
        page=Page.objects.create(title="Grandchild Page", subtitle="Grandchild Subtitle"),
    )

    # Check the routes
    assert root_sitemap.route == "root"
    assert child_sitemap.route == "root/child"
    assert grandchild_sitemap.route == "root/child/grandchild"
