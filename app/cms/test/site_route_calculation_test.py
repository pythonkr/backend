import pytest
from cms.models import Page, Sitemap
from django.core.exceptions import ValidationError


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


@pytest.mark.django_db
def test_get_all_routes():
    # Given: nested한 사이트맵 구조 생성
    data = {
        "root_1": {
            "child_1_1": {"child_1_1_1": {}, "child_1_1_2": {}},
            "child_1_2": {"child_1_2_1": {}},
            "child_1_3": {},
        },
        "root_2": {
            "child_2_1": {"child_2_1_1": {}},
            "child_2_2": {},
        },
    }

    def create_sitemaps(data: dict[str, dict], parent: Sitemap = None) -> None:
        for name, children in data.items():
            sitemap = Sitemap.objects.create(
                route_code=name,
                name=name,
                page=Page.objects.create(title=name, subtitle=f"{name} Subtitle"),
                parent_sitemap=parent,
            )
            create_sitemaps(children, sitemap)

    create_sitemaps(data)

    # When: Sitemap.objects.get_all_routes() 메서드를 호출할 시
    all_routes = Sitemap.objects.get_all_routes()

    # Then: 예상한 모든 route가 나와야 한다.
    assert all_routes == {
        "root_1",
        "root_1/child_1_1",
        "root_1/child_1_1/child_1_1_1",
        "root_1/child_1_1/child_1_1_2",
        "root_1/child_1_2",
        "root_1/child_1_2/child_1_2_1",
        "root_1/child_1_3",
        "root_2",
        "root_2/child_2_1",
        "root_2/child_2_1/child_2_1_1",
        "root_2/child_2_2",
    }


@pytest.mark.parametrize(
    argnames=["route_code", "should_raise"],
    argvalues=[
        ("valid_route", False),
        ("", False),
        ("/invalid_route", True),  # 슬래시로 시작
        ("valid_route_123", False),
        ("valid-route", False),
        ("valid_route_123!", True),  # 특수문자 포함
        ("valid_route_123@", True),  # 특수문자 포함
    ],
)
@pytest.mark.django_db
def test_route_code_validation(route_code: str, should_raise: bool):
    # Given: Sitemap 객체 생성
    sitemap = Sitemap(
        route_code=route_code,
        name="Test Sitemap",
        page=Page.objects.create(title="Test Page", subtitle="Test Subtitle"),
    )

    # When: Validation을 수행
    if should_raise:
        with pytest.raises(ValidationError) as excinfo:
            sitemap.clean()
            assert excinfo.value == "route_code는 알파벳, 숫자, 언더바(_)로만 구성되어야 합니다."
    else:
        sitemap.clean()


@pytest.mark.django_db
def test_clean_should_check_for_self_reference():
    # Given: Sitemap 객체 생성
    sitemap = Sitemap.objects.create(
        route_code="self",
        name="Self Sitemap",
        page=Page.objects.create(title="Self Page", subtitle="Self Subtitle"),
    )

    # When: Self-reference를 만들기 위해 parent_sitemap을 자기 자신으로 설정
    sitemap.parent_sitemap = sitemap

    # Then: ValidationError가 발생해야 한다.
    with pytest.raises(ValidationError) as excinfo:
        sitemap.clean()
        assert excinfo.value == "자기 자신을 부모로 설정할 수 없습니다."


@pytest.mark.django_db
def test_clean_should_check_for_circular_reference():
    # Given: Circular reference가 있는 Sitemap 객체 생성
    root_sitemap = Sitemap.objects.create(
        route_code="root",
        name="Root Sitemap",
        page=Page.objects.create(title="Root Page", subtitle="Root Subtitle"),
    )

    child_sitemap = Sitemap.objects.create(
        route_code="child",
        name="Child Sitemap",
        parent_sitemap=root_sitemap,
        page=Page.objects.create(title="Child Page", subtitle="Child Subtitle"),
    )

    grandchild_sitemap = Sitemap.objects.create(
        route_code="grandchild",
        name="Grandchild Sitemap",
        parent_sitemap=child_sitemap,
        page=Page.objects.create(title="Grandchild Page", subtitle="Grandchild Subtitle"),
    )

    # When: Circular reference를 만들기 위해 child_sitemap을 root_sitemap의 parent로 설정
    root_sitemap.parent_sitemap = grandchild_sitemap

    # Then: ValidationError가 발생해야 한다.
    with pytest.raises(ValidationError) as excinfo:
        root_sitemap.clean()
        assert excinfo.value == "Parent Sitemap이 자식 Sitemap을 가리킬 수 없습니다."


@pytest.mark.django_db
def test_clean_should_check_for_existing_route():
    # Given: 이미 존재하는 route를 가진 Sitemap 객체 생성
    Sitemap.objects.create(
        route_code="existing",
        name="Existing Sitemap",
        page=Page.objects.create(title="Existing Page", subtitle="Existing Subtitle"),
    )

    # When: 새로운 Sitemap 객체를 생성하고, 기존의 route와 같은 route_code를 설정
    new_sitemap = Sitemap(
        route_code="existing",
        name="New Sitemap",
        page=Page.objects.create(title="New Page", subtitle="New Subtitle"),
    )

    # Then: ValidationError가 발생해야 한다.
    with pytest.raises(ValidationError) as excinfo:
        new_sitemap.clean()
        assert excinfo.value == "`existing`라우트는 이미 존재하는 route입니다."
