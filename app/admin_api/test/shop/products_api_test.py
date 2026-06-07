from datetime import datetime, timezone

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)
from shop.conftest import FAR_FUTURE, FAR_PAST
from shop.product.models import Category, CategoryGroup, OptionGroup, Product, Tag
from shop.test.helpers import CategoryGroupsAdminApi, OptionGroupsAdminApi, ProductsAdminApi, TagsAdminApi


@pytest.mark.parametrize("api_cls", [CategoryGroupsAdminApi, TagsAdminApi, ProductsAdminApi])
@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_admin_endpoints_reject_non_superuser_client(request, client_fixture, api_cls):
    response = api_cls(http_client=request.getfixturevalue(client_fixture)).list()
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_category_group_create_with_nested_categories(api_client):
    response = CategoryGroupsAdminApi(http_client=api_client).create(
        {"name": "굿즈", "priority": 0, "categories": [{"name": "셔츠", "priority": 0}]}
    )
    assert response.status_code == HTTP_201_CREATED
    cg = CategoryGroup.objects.get(name="굿즈")
    assert cg.category_set.filter(name="셔츠").exists()


@pytest.mark.django_db
def test_admin_category_group_create_rejects_duplicate_name(api_client):
    CategoryGroup.objects.create(name="굿즈")
    response = CategoryGroupsAdminApi(http_client=api_client).create({"name": "굿즈", "priority": 0})
    # UniqueConstraint → DRF 가 400 으로 변환.
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_tag_create_returns_201(api_client):
    response = TagsAdminApi(http_client=api_client).create({"name_ko": "굿즈", "stock": 0, "max_quantity_per_user": 0})
    assert response.status_code == HTTP_201_CREATED
    assert Tag.objects.filter(name_ko="굿즈").exists()


@pytest.mark.django_db
def test_admin_tag_delete_soft_deletes(api_client):
    tag = Tag.objects.create(name="굿즈")
    response = TagsAdminApi(http_client=api_client).delete(tag.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    tag.refresh_from_db()
    assert tag.deleted_at is not None


@pytest.mark.django_db
def test_admin_product_create_returns_201(api_client, ticket_product):
    response = ProductsAdminApi(http_client=api_client).create(
        {
            "name_ko": "신규 상품",
            "name_en": "New Product",
            "price": 1000,
            "stock": 10,
            "visible_starts_at": FAR_PAST.isoformat(),
            "visible_ends_at": FAR_FUTURE.isoformat(),
            "orderable_starts_at": FAR_PAST.isoformat(),
            "orderable_ends_at": FAR_FUTURE.isoformat(),
            "refundable_ends_at": FAR_FUTURE.isoformat(),
            "category": str(ticket_product.category.id),
        }
    )
    assert response.status_code == HTTP_201_CREATED
    assert Product.objects.filter(name_ko="신규 상품").exists()


@pytest.mark.django_db
def test_admin_product_partial_update_validates_orderable_after_visible_start(api_client, ticket_product):
    # orderable_starts_at(2010) < visible_starts_at(fixture default FAR_PAST=2020) → 400.
    response = ProductsAdminApi(http_client=api_client).update(
        ticket_product.id, {"orderable_starts_at": datetime(2010, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_validates_orderable_before_visible_end(api_client, ticket_product):
    # orderable_ends_at(2100) > visible_ends_at(FAR_FUTURE=2099) → 400.
    response = ProductsAdminApi(http_client=api_client).update(
        ticket_product.id, {"orderable_ends_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_ends_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_rejects_inverted_visible_window(api_client, ticket_product):
    # visible_starts_at(2100) > visible_ends_at(fixture default FAR_FUTURE=2099) → 400.
    response = ProductsAdminApi(http_client=api_client).update(
        ticket_product.id, {"visible_starts_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "visible_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_rejects_inverted_orderable_window(api_client, ticket_product):
    # orderable_starts_at(2098) > orderable_ends_at(fixture default FAR_FUTURE=2099) 인 케이스를 만들기 위해
    # ends_at 을 starts_at 보다 앞으로 patch — orderable_ends_at(2010) < orderable_starts_at(FAR_PAST=2020).
    response = ProductsAdminApi(http_client=api_client).update(
        ticket_product.id, {"orderable_ends_at": datetime(2010, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_merged_uses_instance_value_for_missing_field(api_client, ticket_product):
    # patch 에 visible_starts_at 만 보내고 orderable_* 미포함 → merged 가 instance 값 fallback 사용 → 성공.
    response = ProductsAdminApi(http_client=api_client).update(
        ticket_product.id, {"visible_starts_at": datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_admin_product_delete_soft_deletes(api_client, ticket_product):
    response = ProductsAdminApi(http_client=api_client).delete(ticket_product.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    ticket_product.refresh_from_db()
    assert ticket_product.deleted_at is not None


@pytest.mark.django_db
def test_admin_product_list_filters_by_category(api_client, ticket_product):
    Product.objects.create(
        category=Category.objects.create(
            group=CategoryGroup.objects.create(name="other"),
            name="other",
        ),
        name="other ticket_product",
        price=100,
        visible_starts_at=FAR_PAST,
        visible_ends_at=FAR_FUTURE,
        orderable_starts_at=FAR_PAST,
        orderable_ends_at=FAR_FUTURE,
        refundable_ends_at=FAR_FUTURE,
    )

    response = ProductsAdminApi(http_client=api_client).list({"category": str(ticket_product.category.id)})
    assert response.status_code == HTTP_200_OK
    ids = [p["id"] for p in response.json()]
    assert ids == [str(ticket_product.id)]


@pytest.mark.django_db
def test_admin_option_group_create_rejects_custom_response_without_pattern(api_client, ticket_product):
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {"product": str(ticket_product.id), "name_ko": "요청사항", "name_en": "Req", "is_custom_response": True}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "custom_response_pattern" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_rejects_invalid_regex_pattern(api_client, ticket_product):
    # invalid regex 가 저장되면 주문/수정 validation 시 re.match() runtime error 가 나므로 admin 단에서 막는다.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "요청사항",
            "name_en": "Req",
            "is_custom_response": True,
            "custom_response_pattern": "[unclosed",
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "custom_response_pattern" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_rejects_orderable_starts_before_product_starts(api_client, ticket_product):
    # ticket_product.orderable_starts_at(FAR_PAST=2020) 보다 앞 (2019) → 거절.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "얼리버드",
            "name_en": "Earlybird",
            "orderable_starts_at": datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_rejects_orderable_ends_after_product_ends(api_client, ticket_product):
    # ticket_product.orderable_ends_at(FAR_FUTURE=2099) 보다 뒤 (2100) → 거절.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "후반",
            "name_en": "Late",
            "orderable_ends_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_ends_at" in str(response.json())


@pytest.mark.parametrize("kind", ["visible", "orderable"])
@pytest.mark.django_db
def test_admin_option_group_create_rejects_inverted_window(api_client, ticket_product, kind):
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "옵션",
            "name_en": "Opt",
            f"{kind}_starts_at": datetime(2050, 1, 1, tzinfo=timezone.utc).isoformat(),
            f"{kind}_ends_at": datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert f"{kind}_starts_at" in str(response.json())


@pytest.mark.parametrize("kind", ["visible", "orderable"])
@pytest.mark.django_db
def test_admin_option_group_create_rejects_starts_before_product_starts(api_client, ticket_product, kind):
    # group_starts_at < product_starts_at (FAR_PAST=2020) → 거절. visible / orderable 동일 분기.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "옵션",
            "name_en": "Opt",
            f"{kind}_starts_at": datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert f"{kind}_starts_at" in str(response.json())


@pytest.mark.parametrize("kind", ["visible", "orderable"])
@pytest.mark.django_db
def test_admin_option_group_create_rejects_ends_after_product_ends(api_client, ticket_product, kind):
    # group_ends_at > product_ends_at (FAR_FUTURE=2099) → 거절.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "옵션",
            "name_en": "Opt",
            f"{kind}_ends_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert f"{kind}_ends_at" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_allows_period_within_product_window(api_client, ticket_product):
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "얼리버드",
            "name_en": "Earlybird",
            "orderable_starts_at": datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
            "orderable_ends_at": datetime(2031, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_201_CREATED


@pytest.mark.parametrize(
    "window_field",
    ["visible_starts_at", "visible_ends_at", "orderable_starts_at", "orderable_ends_at"],
)
@pytest.mark.django_db
def test_admin_option_group_create_rejects_required_group_with_explicit_window(
    api_client, ticket_product, window_field
):
    # min_quantity_per_product >= 1 인 필수 그룹은 visible/orderable starts_at/ends_at 을 별도 지정할 수 없음 —
    # 그룹 윈도우가 상품과 어긋나면 필수 옵션이 비어 상품을 살 수 없는 죽은 구간이 생긴다.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "필수옵션",
            "name_en": "Required",
            "min_quantity_per_product": 1,
            window_field: datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert window_field in str(response.json())


@pytest.mark.parametrize(
    "window_field",
    ["visible_starts_at", "visible_ends_at", "orderable_starts_at", "orderable_ends_at"],
)
@pytest.mark.django_db
def test_admin_option_group_partial_update_rejects_setting_min_quantity_when_window_already_set(
    api_client, ticket_product, window_field
):
    # 역방향 — 윈도우가 이미 설정된 그룹을 min_quantity_per_product>=1 로 patch → merged 가 instance 윈도우를 사용해 거절.
    group = OptionGroup.objects.create(
        product=ticket_product, name="기간옵션", **{window_field: datetime(2030, 1, 1, tzinfo=timezone.utc)}
    )
    response = OptionGroupsAdminApi(http_client=api_client).update(group.id, {"min_quantity_per_product": 1})
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert window_field in str(response.json())


@pytest.mark.parametrize("kind", ["visible", "orderable"])
@pytest.mark.django_db
def test_admin_option_group_create_rejects_ends_at_before_product_starts_at(api_client, ticket_product, kind):
    # P2-A: 한 쪽 boundary 만 명시 — starts_at=None → ticket_product fallback(FAR_PAST=2020), ends_at=2019.
    # admin 이 model effective_*_period 의 inverted 케이스를 차단해야 함.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "옵션",
            "name_en": "Opt",
            f"{kind}_ends_at": datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert f"{kind}_ends_at" in str(response.json())


@pytest.mark.parametrize("kind", ["visible", "orderable"])
@pytest.mark.django_db
def test_admin_option_group_create_rejects_starts_at_after_product_ends_at(api_client, ticket_product, kind):
    # P2-A: starts_at=2100 > ticket_product.*_ends_at(FAR_FUTURE=2099) → effective inverted.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "옵션",
            "name_en": "Opt",
            f"{kind}_starts_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert f"{kind}_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_allows_non_required_group_with_explicit_window(api_client, ticket_product):
    # 비필수 그룹(min_quantity_per_product=0) 은 starts_at 명시 가능.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(ticket_product.id),
            "name_ko": "선택옵션",
            "name_en": "Optional",
            "orderable_starts_at": datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert response.status_code == HTTP_201_CREATED


@pytest.mark.parametrize("status", list(Product.CurrentStatus))
@pytest.mark.django_db
def test_admin_product_list_filters_by_status(api_client, products_by_status, status):
    response = ProductsAdminApi(http_client=api_client).list({"status": status.value})
    assert response.status_code == HTTP_200_OK
    assert [p["id"] for p in response.json()] == [str(products_by_status[status].id)]
