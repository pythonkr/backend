import pytest
from django.urls import reverse
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)
from shop.order.models import OrderProductRelationTag

LIST_URL = reverse("v1:admin-shop-order-product-relation-tag-list")


def _assign_url(tag_id, action: str = "assign") -> str:
    return reverse(f"v1:admin-shop-order-product-relation-tag-{action}", args=[tag_id])


@pytest.fixture
def speaker_tag(db) -> OrderProductRelationTag:
    return OrderProductRelationTag.objects.create(code="speaker", name="발표자")


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_tag_list_rejects_non_superuser(request, client_fixture):
    assert request.getfixturevalue(client_fixture).get(LIST_URL).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_tag_create_and_reject_duplicated_code(api_client):
    create = api_client.post(LIST_URL, {"code": "speaker", "name": "발표자", "priority": 1}, format="json")
    assert create.status_code == HTTP_201_CREATED

    duplicated = api_client.post(LIST_URL, {"code": "speaker", "name": "다른 이름"}, format="json")
    assert duplicated.status_code == HTTP_400_BAD_REQUEST
    assert "code" in str(duplicated.json())


@pytest.mark.django_db
def test_tag_create_allows_code_of_soft_deleted_tag(api_client):
    OrderProductRelationTag.objects.create(code="speaker", name="발표자").delete()

    assert api_client.post(LIST_URL, {"code": "speaker", "name": "발표자"}, format="json").status_code == (
        HTTP_201_CREATED
    )


@pytest.mark.django_db
def test_assign_attaches_tag_to_filtered_order_products(api_client, speaker_tag, order_factory):
    order = order_factory(status="completed")
    order_product = order.products.get()

    response = api_client.post(f"{_assign_url(speaker_tag.id)}?order_id={order.id}")

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"affected": 1}
    assert list(order_product.tags.all()) == [speaker_tag]


@pytest.mark.django_db
def test_assign_is_idempotent(api_client, speaker_tag, order_factory):
    order = order_factory(status="completed")
    url = f"{_assign_url(speaker_tag.id)}?order_id={order.id}"

    api_client.post(url)
    api_client.post(url)

    assert order.products.get().tags.count() == 1


@pytest.mark.django_db
def test_assign_skips_order_products_outside_the_filter(api_client, speaker_tag, order_factory):
    order_factory(status="completed")
    other_order = order_factory(status="completed")

    api_client.post(f"{_assign_url(speaker_tag.id)}?order_id={other_order.id}")

    assert speaker_tag.order_product_relations.count() == 1


@pytest.mark.django_db
def test_assign_rejects_request_without_any_filter(api_client, speaker_tag, order_factory):
    order_factory(status="completed")

    response = api_client.post(_assign_url(speaker_tag.id))

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "조회 조건" in str(response.json())
    assert speaker_tag.order_product_relations.count() == 0


@pytest.mark.django_db
def test_unassign_detaches_tag(api_client, speaker_tag, order_factory):
    order = order_factory(status="completed")
    speaker_tag.order_product_relations.add(order.products.get())

    response = api_client.post(f"{_assign_url(speaker_tag.id, 'unassign')}?order_id={order.id}")

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"affected": 1}
    assert speaker_tag.order_product_relations.count() == 0


@pytest.mark.django_db
def test_order_detail_exposes_tags(api_client, speaker_tag, order_factory):
    order = order_factory(status="completed")
    speaker_tag.order_product_relations.add(order.products.get())

    body = api_client.get(reverse("v1:admin-shop-order-detail", args=[order.id])).json()

    assert body["products"][0]["tags"] == [{"id": str(speaker_tag.id), "code": "speaker", "name": "발표자"}]


@pytest.mark.django_db
def test_assign_rejects_blank_filter_value(api_client, speaker_tag, order_factory):
    # django-filter 는 빈 값을 무시하므로 `?id=` 가 전체 태깅이 되면 안 된다.
    order_factory(status="completed")

    response = api_client.post(f"{_assign_url(speaker_tag.id)}?id=")

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert speaker_tag.order_product_relations.count() == 0
