import http

import pytest
from cms.models import DomainGroup, Page, Section, Sitemap
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def domain_group(superuser):
    return DomainGroup.objects.create(
        name="2025년 PyConKR 홈페이지",
        domains=["2025.pycon.kr"],
        created_by=superuser,
        updated_by=superuser,
    )


# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_request_to_domain_group_is_rejected():
    response = APIClient().get(reverse("v1:admin-domain-group-list"))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


# ---- DomainGroup CRUD -------------------------------------------------------


@pytest.mark.django_db
def test_domain_group_list(api_client, domain_group):
    response = api_client.get(reverse("v1:admin-domain-group-list"))
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()
    assert any(row["name"] == domain_group.name for row in rows)


@pytest.mark.django_db
def test_domain_group_create(api_client):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": "2026년 PyConKR 홈페이지", "domains": ["2026.pycon.kr", "pycon.kr"]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED, response.json()
    assert DomainGroup.objects.filter(name="2026년 PyConKR 홈페이지").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "domains",
    [
        ["https://pycon.kr"],  # 스킴
        ["pycon.kr:8080"],  # 포트
        ["pycon.kr/path"],  # 경로
        ["pycon.kr?q=1"],  # 쿼리
        ["pycon..kr"],  # 연속 점
        [],  # 빈 배열
    ],
)
def test_domain_group_create_rejects_invalid_domains(api_client, domains):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": "bad", "domains": domains},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
@pytest.mark.parametrize(
    "input_domains,expected",
    [
        (["PYCON.KR"], ["pycon.kr"]),
        ([" pycon.kr "], ["pycon.kr"]),
        (["pycon.kr", "PYCON.KR"], ["pycon.kr"]),
        (["pycon.kr", "pycon.kr"], ["pycon.kr"]),
    ],
)
def test_domain_group_create_normalizes_domains(api_client, input_domains, expected):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": "n", "domains": input_domains},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED, response.json()
    assert response.json()["domains"] == expected


# ---- DB-level overlap trigger (race-safe) -----------------------------------


@pytest.mark.django_db(transaction=True)
def test_db_trigger_rejects_overlapping_domain_on_insert():
    DomainGroup.objects.create(name="A", domains=["x.pycon.kr"])
    with pytest.raises(IntegrityError):
        DomainGroup.objects.create(name="B", domains=["x.pycon.kr", "y.pycon.kr"])


@pytest.mark.django_db(transaction=True)
def test_db_trigger_rejects_overlapping_domain_on_update():
    DomainGroup.objects.create(name="A", domains=["x.pycon.kr"])
    other = DomainGroup.objects.create(name="B", domains=["y.pycon.kr"])
    with pytest.raises(IntegrityError):
        other.domains = ["x.pycon.kr"]
        other.save()


@pytest.mark.django_db(transaction=True)
def test_db_trigger_ignores_soft_deleted_groups():
    a = DomainGroup.objects.create(name="A", domains=["x.pycon.kr"])
    a.delete()
    DomainGroup.objects.create(name="B", domains=["x.pycon.kr"])  # 같은 도메인 재사용 허용


# ---- DomainGroup constraints ------------------------------------------------


@pytest.mark.django_db
def test_domain_group_create_rejects_overlapping_domain(api_client, domain_group):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": "다른 그룹", "domains": ["2025.pycon.kr", "new.pycon.kr"]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_domain_group_update_can_keep_own_domains(api_client, domain_group):
    response = api_client.patch(
        reverse("v1:admin-domain-group-detail", kwargs={"pk": domain_group.id}),
        data={"domains": ["2025.pycon.kr", "another.pycon.kr"]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    domain_group.refresh_from_db()
    assert set(domain_group.domains) == {"2025.pycon.kr", "another.pycon.kr"}


@pytest.mark.django_db
def test_domain_group_create_rejects_duplicate_name(api_client, domain_group):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": domain_group.name, "domains": ["new.pycon.kr"]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- DomainGroup auto-creates default Sitemap -------------------------------


@pytest.mark.django_db
def test_creating_domain_group_auto_creates_default_sitemap_page_section(api_client):
    response = api_client.post(
        reverse("v1:admin-domain-group-list"),
        data={"name": "신규 그룹", "domains": ["new.pycon.kr"]},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.CREATED, response.json()

    group = DomainGroup.objects.get(name="신규 그룹")
    sitemaps = list(group.sitemaps.filter_active())
    assert len(sitemaps) == 1
    assert sitemaps[0].name == "신규 그룹"
    assert sitemaps[0].route_code == ""

    page = sitemaps[0].page
    assert page is not None
    assert page.title == "신규 그룹"
    assert Section.objects.filter_active().filter(page=page).count() == 1


@pytest.mark.django_db
def test_updating_empty_group_auto_creates_default_sitemap(api_client, domain_group):
    assert domain_group.sitemaps.filter_active().count() == 0

    response = api_client.patch(
        reverse("v1:admin-domain-group-detail", kwargs={"pk": domain_group.id}),
        data={"name": "수정된 이름"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert domain_group.sitemaps.filter_active().count() == 1


@pytest.mark.django_db
def test_updating_non_empty_group_does_not_create_extra_sitemap(api_client, superuser, domain_group):
    page = Page.objects.create(title="t", subtitle="s", created_by=superuser, updated_by=superuser)
    Sitemap.objects.create(
        name="existing",
        page=page,
        domain_group=domain_group,
        created_by=superuser,
        updated_by=superuser,
    )
    assert domain_group.sitemaps.filter_active().count() == 1

    response = api_client.patch(
        reverse("v1:admin-domain-group-detail", kwargs={"pk": domain_group.id}),
        data={"name": "수정된 이름"},
        format="json",
    )
    assert response.status_code == http.HTTPStatus.OK, response.json()
    assert domain_group.sitemaps.filter_active().count() == 1


# ---- DomainGroup destroy ----------------------------------------------------


@pytest.mark.django_db
def test_destroy_domain_group_with_lone_root_succeeds_leaving_page(api_client, superuser):
    # lone root만 함께 삭제. Page/Section은 보존 (dangling이 되더라도 의도적 삭제 회피로 안전성 우선).
    group = DomainGroup.objects.create(name="A", domains=["a.pycon.kr"], created_by=superuser, updated_by=superuser)
    page = Page.objects.create(title="A", subtitle="A", created_by=superuser, updated_by=superuser)
    section = Section.objects.create(page=page, order=0, body="", created_by=superuser, updated_by=superuser)
    sitemap = Sitemap.objects.create(
        name="root", domain_group=group, route_code="", page=page, created_by=superuser, updated_by=superuser
    )

    response = api_client.delete(reverse("v1:admin-domain-group-detail", kwargs={"pk": group.id}))
    assert response.status_code == http.HTTPStatus.NO_CONTENT

    group.refresh_from_db()
    sitemap.refresh_from_db()
    page.refresh_from_db()
    section.refresh_from_db()
    assert group.deleted_at is not None
    assert sitemap.deleted_at is not None
    assert page.deleted_at is None
    assert section.deleted_at is None


@pytest.mark.django_db
def test_destroy_domain_group_with_multiple_sitemaps_rejected(api_client, superuser):
    group = DomainGroup.objects.create(name="A", domains=["a.pycon.kr"], created_by=superuser, updated_by=superuser)
    Sitemap.objects.create(name="r1", domain_group=group, route_code="", created_by=superuser, updated_by=superuser)
    Sitemap.objects.create(
        name="r2", domain_group=group, route_code="other", created_by=superuser, updated_by=superuser
    )

    response = api_client.delete(reverse("v1:admin-domain-group-detail", kwargs={"pk": group.id}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST

    group.refresh_from_db()
    assert group.deleted_at is None


@pytest.mark.django_db
def test_destroy_domain_group_with_sitemap_having_children_rejected(api_client, superuser):
    group = DomainGroup.objects.create(name="A", domains=["a.pycon.kr"], created_by=superuser, updated_by=superuser)
    parent = Sitemap.objects.create(
        name="parent", domain_group=group, route_code="", created_by=superuser, updated_by=superuser
    )
    Sitemap.objects.create(
        name="child",
        domain_group=group,
        route_code="child",
        parent_sitemap=parent,
        created_by=superuser,
        updated_by=superuser,
    )

    response = api_client.delete(reverse("v1:admin-domain-group-detail", kwargs={"pk": group.id}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST

    group.refresh_from_db()
    assert group.deleted_at is None


# ---- Sitemap admin serializer exposes domain_group --------------------------


@pytest.mark.django_db
def test_sitemap_admin_serializer_exposes_domain_group(api_client, superuser, domain_group):
    page = Page.objects.create(title="t", subtitle="s", created_by=superuser, updated_by=superuser)
    sitemap = Sitemap.objects.create(
        name="x",
        page=page,
        domain_group=domain_group,
        created_by=superuser,
        updated_by=superuser,
    )

    response = api_client.get(reverse("v1:admin-sitemap-list"))
    assert response.status_code == http.HTTPStatus.OK

    rows = response.json()
    row = next(r for r in rows if r["id"] == str(sitemap.id))
    assert row["domain_group"] == str(domain_group.id)


@pytest.mark.django_db
def test_sitemap_admin_filter_by_domain_group(api_client, superuser):
    group_a = DomainGroup.objects.create(name="A", domains=["a.pycon.kr"], created_by=superuser, updated_by=superuser)
    group_b = DomainGroup.objects.create(name="B", domains=["b.pycon.kr"], created_by=superuser, updated_by=superuser)
    page = Page.objects.create(title="t", subtitle="s", created_by=superuser, updated_by=superuser)

    sitemap_a = Sitemap.objects.create(
        name="A-sitemap", page=page, domain_group=group_a, created_by=superuser, updated_by=superuser
    )
    Sitemap.objects.create(
        name="B-sitemap", page=page, domain_group=group_b, created_by=superuser, updated_by=superuser
    )

    response = api_client.get(reverse("v1:admin-sitemap-list"), {"domain_group": str(group_a.id)})
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()
    assert {r["id"] for r in rows} == {str(sitemap_a.id)}
