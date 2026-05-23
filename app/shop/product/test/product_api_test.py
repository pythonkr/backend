from datetime import datetime, timezone

import pytest
from freezegun import freeze_time
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND
from shop.order.models import Order, OrderProductRelation
from shop.product.models import Product
from shop.product.serializers.dto import ProductDto
from shop.test.helpers import ProductsApi


@pytest.mark.django_db
def test_product_list_returns_visible_products(anon_client, product):
    # ViewSet 의 get_queryset 이 prefetch 추가하므로 같은 prefetch 로 직렬화 비교 — N+1 회피 + 직렬화 동등.
    expected_qs = (
        Product.objects.filter(id=product.id)
        .select_related("category", "category__group", "image")
        .prefetch_related("tags", "option_groups__options")
    )
    response = ProductsApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == ProductDto(instance=expected_qs, many=True).data


@pytest.mark.django_db
def test_product_list_excludes_hidden_products(anon_client, product):
    product.hidden = True
    product.save()
    response = ProductsApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_list_excludes_products_outside_visible_window(anon_client, product):
    response = ProductsApi(http_client=anon_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_product_retrieve_returns_active_product(anon_client, product):
    response = ProductsApi(http_client=anon_client).retrieve(product.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == ProductDto(instance=product).data


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_retrieve_returns_404_for_anonymous_when_outside_visible_window(anon_client, product):
    response = ProductsApi(http_client=anon_client).retrieve(product.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@freeze_time(datetime(2010, 1, 1, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_product_retrieve_allows_purchaser_to_see_out_of_window_product(customer_client, customer_user, product):
    # 사용자가 구매한 상품은 노출 윈도우 밖이어도 retrieve 가능.
    OrderProductRelation.objects.create(
        order=Order.objects.create(user=customer_user, name="x"),
        product=product,
        price=product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    response = ProductsApi(http_client=customer_client).retrieve(product.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == ProductDto(instance=product).data
