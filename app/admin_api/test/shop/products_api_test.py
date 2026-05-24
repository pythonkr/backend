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
from shop.product.models import Category, CategoryGroup, Product, Tag
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
def test_admin_product_create_returns_201(api_client, product):
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
            "category": str(product.category.id),
        }
    )
    assert response.status_code == HTTP_201_CREATED
    assert Product.objects.filter(name_ko="신규 상품").exists()


@pytest.mark.django_db
def test_admin_product_partial_update_validates_orderable_after_visible_start(api_client, product):
    # orderable_starts_at(2010) < visible_starts_at(fixture default FAR_PAST=2020) → 400.
    response = ProductsAdminApi(http_client=api_client).update(
        product.id, {"orderable_starts_at": datetime(2010, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_starts_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_validates_orderable_before_visible_end(api_client, product):
    # orderable_ends_at(2100) > visible_ends_at(FAR_FUTURE=2099) → 400.
    response = ProductsAdminApi(http_client=api_client).update(
        product.id, {"orderable_ends_at": datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "orderable_ends_at" in str(response.json())


@pytest.mark.django_db
def test_admin_product_partial_update_merged_uses_instance_value_for_missing_field(api_client, product):
    # patch 에 visible_starts_at 만 보내고 orderable_* 미포함 → merged 가 instance 값 fallback 사용 → 성공.
    response = ProductsAdminApi(http_client=api_client).update(
        product.id, {"visible_starts_at": datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat()}
    )
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_admin_product_delete_soft_deletes(api_client, product):
    response = ProductsAdminApi(http_client=api_client).delete(product.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    product.refresh_from_db()
    assert product.deleted_at is not None


@pytest.mark.django_db
def test_admin_product_list_filters_by_category(api_client, product):
    Product.objects.create(
        category=Category.objects.create(
            group=CategoryGroup.objects.create(name="other"),
            name="other",
        ),
        name="other product",
        price=100,
        visible_starts_at=FAR_PAST,
        visible_ends_at=FAR_FUTURE,
        orderable_starts_at=FAR_PAST,
        orderable_ends_at=FAR_FUTURE,
        refundable_ends_at=FAR_FUTURE,
    )

    response = ProductsAdminApi(http_client=api_client).list({"category": str(product.category.id)})
    assert response.status_code == HTTP_200_OK
    ids = [p["id"] for p in response.json()]
    assert ids == [str(product.id)]


@pytest.mark.django_db
def test_admin_option_group_create_rejects_custom_response_without_pattern(api_client, product):
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {"product": str(product.id), "name_ko": "요청사항", "name_en": "Req", "is_custom_response": True}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "custom_response_pattern" in str(response.json())


@pytest.mark.django_db
def test_admin_option_group_create_rejects_invalid_regex_pattern(api_client, product):
    # invalid regex 가 저장되면 주문/수정 validation 시 re.match() runtime error 가 나므로 admin 단에서 막는다.
    response = OptionGroupsAdminApi(http_client=api_client).create(
        {
            "product": str(product.id),
            "name_ko": "요청사항",
            "name_en": "Req",
            "is_custom_response": True,
            "custom_response_pattern": "[unclosed",
        }
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "custom_response_pattern" in str(response.json())


@pytest.mark.parametrize("status", list(Product.CurrentStatus))
@pytest.mark.django_db
def test_admin_product_list_filters_by_status(api_client, products_by_status, status):
    response = ProductsAdminApi(http_client=api_client).list({"status": status.value})
    assert response.status_code == HTTP_200_OK
    assert [p["id"] for p in response.json()] == [str(products_by_status[status].id)]
