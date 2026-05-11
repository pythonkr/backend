import http

import pytest
from cms.models import DomainGroup, Page, Sitemap
from django.urls import reverse


def _create_sitemap(route_code: str, *, group: DomainGroup) -> Sitemap:
    return Sitemap.objects.create(
        route_code=route_code,
        name=route_code,
        page=Page.objects.create(title=route_code, subtitle=route_code),
        domain_group=group,
    )


@pytest.mark.django_db
def test_list_view(api_client, create_sitemap):
    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url, {"frontend-domain": "test.pycon.kr"})
    assert response.status_code == http.HTTPStatus.OK


@pytest.mark.django_db
def test_list_view_returns_only_matching_domain(api_client):
    group_main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    group_legacy = DomainGroup.objects.create(name="legacy", domains=["legacy.pycon.kr"])

    _create_sitemap("main_about", group=group_main)
    _create_sitemap("legacy_about", group=group_legacy)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url, {"frontend-domain": "pycon.kr"})

    assert response.status_code == http.HTTPStatus.OK
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"main_about"}


@pytest.mark.django_db
def test_list_view_returns_404_when_no_domain_context(api_client, create_sitemap):
    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url)
    assert response.status_code == http.HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_list_view_returns_empty_when_domain_does_not_match(api_client):
    group = DomainGroup.objects.create(name="g", domains=["pycon.kr"])
    _create_sitemap("about", group=group)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url, {"frontend-domain": "other.kr"})
    assert response.data == []


@pytest.mark.django_db
def test_priority_query_param_wins_over_header(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    other = DomainGroup.objects.create(name="other", domains=["other.kr"])
    _create_sitemap("main_route", group=main)
    _create_sitemap("other_route", group=other)

    url = reverse("v1:cms-sitemap-list")
    # query=other.kr이지만 header=pycon.kr — query가 이겨서 other 그룹만 나와야 함
    response = api_client.get(
        url,
        {"frontend-domain": "other.kr"},
        HTTP_X_FRONTEND_DOMAIN="pycon.kr",
        HTTP_ORIGIN="https://pycon.kr",
        HTTP_REFERER="https://pycon.kr/foo",
    )
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"other_route"}


@pytest.mark.django_db
def test_priority_header_wins_over_origin(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    other = DomainGroup.objects.create(name="other", domains=["other.kr"])
    _create_sitemap("main_route", group=main)
    _create_sitemap("other_route", group=other)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(
        url,
        HTTP_X_FRONTEND_DOMAIN="other.kr",
        HTTP_ORIGIN="https://pycon.kr",
        HTTP_REFERER="https://pycon.kr/foo",
    )
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"other_route"}


@pytest.mark.django_db
def test_priority_origin_wins_over_referer(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    other = DomainGroup.objects.create(name="other", domains=["other.kr"])
    _create_sitemap("main_route", group=main)
    _create_sitemap("other_route", group=other)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(
        url,
        HTTP_ORIGIN="https://pycon.kr",
        HTTP_REFERER="https://other.kr/foo",
    )
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"main_route"}


@pytest.mark.django_db
def test_referer_used_when_no_other_signals(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    _create_sitemap("main_route", group=main)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url, HTTP_REFERER="https://pycon.kr/some/path")
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"main_route"}


@pytest.mark.django_db
def test_normalization_strips_scheme_port_and_lowercases(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    _create_sitemap("main_route", group=main)

    url = reverse("v1:cms-sitemap-list")
    # 대문자 + 포트 + 스킴 + 경로가 모두 정규화되어 'pycon.kr'로 매칭되어야 함
    response = api_client.get(url, HTTP_ORIGIN="HTTPS://PYCON.KR:8080")
    route_codes = {item["route_code"] for item in response.data}
    assert route_codes == {"main_route"}


@pytest.mark.django_db
def test_serializer_does_not_expose_domain_group(api_client):
    main = DomainGroup.objects.create(name="main", domains=["pycon.kr"])
    _create_sitemap("main_route", group=main)

    url = reverse("v1:cms-sitemap-list")
    response = api_client.get(url, {"frontend-domain": "pycon.kr"})

    assert response.data
    assert "domain_group" not in response.data[0]
