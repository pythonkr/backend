from datetime import datetime, timezone

import pytest
from admin_api.test.helpers import CategoryGroupsAdminApi, OptionGroupsAdminApi, ProductsAdminApi, TagsAdminApi
from django.urls import reverse
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)
from shop.conftest import FAR_FUTURE, FAR_PAST
from shop.order.models import OrderProductOptionRelation
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, Tag

PRODUCT_SELECTABLES_URL = reverse("v1:admin-shop-product-list") + "selectables/"


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
def test_admin_category_group_selectables_include_priority_meta(api_client):
    # selectables 의 각 그룹은 CategoryGroup.get_choice_meta() 로 priority 메타를 실어야 한다.
    group = CategoryGroup.objects.create(name="굿즈", priority=7)
    url = reverse("v1:admin-shop-category-group-list") + "selectables/"
    response = api_client.get(url)
    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert {c["const"]: c for c in body["results"]}[str(group.id)]["meta"]["priority"] == 7
    assert "priority" in body["meta_schema"]


def _patch_category(api_client, category: Category, **fields) -> object:
    # 카테고리는 CategoryGroup nested 로만 수정 — 그룹에 카테고리 1개뿐이므로 단건 전송이 전체 목록.
    return CategoryGroupsAdminApi(http_client=api_client).update(
        category.group_id, {"categories": [{"id": str(category.id), "name": category.name, **fields}]}
    )


@pytest.mark.django_db
def test_admin_category_is_ticket_unset_blocked_when_certificate_issued(api_client, issued_document):
    category = issued_document.issuable.product.category
    response = CategoryGroupsAdminApi(http_client=api_client).update(
        category.group_id,
        {"categories": [{"id": str(category.id), "is_ticket": False}]},
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    category.refresh_from_db()
    assert category.is_ticket is True


@pytest.mark.django_db
def test_admin_category_event_unset_blocked_when_certificate_issued(api_client, issued_document):
    category = issued_document.issuable.product.category
    response = CategoryGroupsAdminApi(http_client=api_client).update(
        category.group_id,
        {"categories": [{"id": str(category.id), "event": None}]},
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    category.refresh_from_db()
    assert category.event_id is not None


@pytest.mark.django_db
def test_admin_category_update_allowed_when_certificate_issued_without_unset(api_client, issued_document):
    # 발급 이력이 있어도 is_ticket/event 를 유지(미해제)하면 수정 허용.
    category = issued_document.issuable.product.category
    response = CategoryGroupsAdminApi(http_client=api_client).update(
        category.group_id,
        {"categories": [{"id": str(category.id), "name": "이름만 변경"}]},
    )
    assert response.status_code == HTTP_200_OK
    category.refresh_from_db()
    assert category.is_ticket is True
    assert category.event_id is not None


@pytest.mark.django_db
def test_admin_category_is_ticket_unset_allowed_without_certificate(api_client):
    # 발급 이력이 없는 카테고리는 자유롭게 is_ticket 해제 가능.
    group = CategoryGroup.objects.create(name="굿즈")
    category = Category.objects.create(group=group, name="셔츠", is_ticket=True)
    response = CategoryGroupsAdminApi(http_client=api_client).update(
        group.id,
        {"categories": [{"id": str(category.id), "is_ticket": False}]},
    )
    assert response.status_code == HTTP_200_OK
    category.refresh_from_db()
    assert category.is_ticket is False


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
def test_admin_product_create_allows_zero_price(api_client, ticket_product):
    response = ProductsAdminApi(http_client=api_client).create(
        {
            "name_ko": "무료 튜토리얼",
            "name_en": "Free Tutorial",
            "price": 0,
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
    assert response.json()["price"] == 0
    assert Product.objects.filter(name_ko="무료 튜토리얼", price=0).exists()


@pytest.mark.django_db
def test_admin_product_partial_update_can_set_refundable_ends_at_null(api_client, ticket_product):
    # null = 환불 불가 상품. 운영자가 어드민에서 직접 지정하는 경로.
    response = ProductsAdminApi(http_client=api_client).update(ticket_product.id, {"refundable_ends_at": None})
    assert response.status_code == HTTP_200_OK
    ticket_product.refresh_from_db()
    assert ticket_product.refundable_ends_at is None


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
    ids = [p["id"] for p in response.json()["results"]]
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
    assert [p["id"] for p in response.json()["results"]] == [str(products_by_status[status].id)]


@pytest.mark.django_db
def test_admin_product_selectables_include_meta(api_client, ticket_product):
    # selectables 결과의 각 product 는 Product.get_choice_meta() 로 category/price/stock/status 메타를 실어야 한다.
    response = api_client.get(PRODUCT_SELECTABLES_URL)
    assert response.status_code == HTTP_200_OK
    body = response.json()
    product_meta = {p["const"]: p for p in body["results"]}[str(ticket_product.id)]["meta"]
    assert (
        product_meta.items()
        >= {
            "category": str(ticket_product.category),
            "price": ticket_product.price,
            "stock": ticket_product.stock,
            "status": Product.CurrentStatus.ACTIVE.label,
        }.items()
    )
    # meta_schema 는 모델의 choices_meta_schema 를 반영한다.
    assert {"category", "price", "stock", "status"} <= set(body["meta_schema"])


@pytest.fixture
def sold_option(order_factory, option_group) -> Option:
    """paid OPR 2건이 붙은 옵션 — sold_count=2, stock=10."""
    sized = option_group.options.create(name="M", stock=10)
    for _ in range(2):
        OrderProductOptionRelation.objects.create(
            order_product_relation=order_factory(status="completed").products.get(),
            product_option_group=option_group,
            product_option=sized,
        )
    return sized


def _option_payload(option: Option, *, stock: int) -> dict:
    # nested options 는 전량 동기화라 유지할 옵션을 모두 실어야 한다 (누락 시 soft delete).
    return {"options": [{"id": str(option.id), "name_ko": option.name_ko, "name_en": option.name_en, "stock": stock}]}


@pytest.mark.django_db
def test_admin_option_update_rejects_stock_below_sold_count(api_client, option_group, sold_option):
    # 이미 2개 팔린 옵션에 stock=1 → leftover_stock 이 -1 이 되는 유일한 입력 경로라 거절.
    response = OptionGroupsAdminApi(http_client=api_client).update(
        option_group.id, _option_payload(sold_option, stock=1)
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "이미 2개가 판매된 옵션입니다" in str(response.json())
    sold_option.refresh_from_db()
    assert sold_option.stock == 10


@pytest.mark.django_db
def test_admin_option_update_allows_stock_equal_to_sold_count(api_client, option_group, sold_option):
    # 판매 수량과 같은 값 = leftover 0 (판매 마감) — 운영자가 실제로 쓰는 마감 방식이라 허용.
    response = OptionGroupsAdminApi(http_client=api_client).update(
        option_group.id, _option_payload(sold_option, stock=2)
    )
    assert response.status_code == HTTP_200_OK
    sold_option.refresh_from_db()
    assert sold_option.stock == 2
    assert sold_option.leftover_stock == 0


@pytest.mark.django_db
def test_admin_option_update_allows_zero_stock_as_unlimited(api_client, option_group, sold_option):
    response = OptionGroupsAdminApi(http_client=api_client).update(
        option_group.id, _option_payload(sold_option, stock=0)
    )
    assert response.status_code == HTTP_200_OK
    sold_option.refresh_from_db()
    assert sold_option.leftover_stock is None


@pytest.mark.django_db
def test_admin_option_update_allows_negative_stock_when_nothing_sold(api_client, option_group, option):
    # 판매 이력 없는 옵션을 품절 노출시키는 관용구(-1) — stock=0 이 무제한이라 이 방법뿐이므로 막지 않는다.
    response = OptionGroupsAdminApi(http_client=api_client).update(option_group.id, _option_payload(option, stock=-1))
    assert response.status_code == HTTP_200_OK
    option.refresh_from_db()
    assert option.stock == -1


@pytest.mark.django_db
def test_admin_option_group_retrieve_exposes_sold_count(api_client, option_group, sold_option):
    # stock=0 이면 leftover_stock 이 null 이라 어드민에서 판매 수량을 볼 수 없었다 — sold_count 로 항상 노출.
    response = OptionGroupsAdminApi(http_client=api_client).retrieve(option_group.id)
    assert response.status_code == HTTP_200_OK
    payload = {o["id"]: o for o in response.json()["options"]}[str(sold_option.id)]
    assert payload["sold_count"] == 2
    assert payload["leftover_stock"] == 8
