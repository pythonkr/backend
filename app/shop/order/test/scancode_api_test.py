import uuid

import pytest
import shortuuid
from django.conf import settings
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND
from shop.order.models import Order
from shop.test.helpers import ScanCodeApi


@pytest.mark.django_db
def test_scancode_rejects_missing_token(anon_client):
    response = ScanCodeApi(http_client=anon_client).list()
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_scancode_rejects_invalid_token_format(anon_client):
    response = ScanCodeApi(http_client=anon_client).list({"token": "garbage"})
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_scancode_user_token_returns_user_orders(anon_client, customer_user, order_factory):
    order_factory(status="completed")
    response = ScanCodeApi(http_client=anon_client).list({"token": customer_user.scancode_token})
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_scancode_user_token_rejects_when_all_orders_refunded(anon_client, customer_user, order_factory):
    order_factory(status="refunded")
    response = ScanCodeApi(http_client=anon_client).list({"token": customer_user.scancode_token})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_scancode_order_token_returns_order(anon_client, order_factory):
    completed_order = order_factory(status="completed")
    response = ScanCodeApi(http_client=anon_client).list({"token": completed_order.scancode_token})
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_scancode_order_token_rejects_refunded_order(anon_client, order_factory):
    refunded_order = order_factory(status="refunded")
    response = ScanCodeApi(http_client=anon_client).list({"token": refunded_order.scancode_token})
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_scancode_order_token_allows_order_without_payment_history(anon_client, customer_user):
    # current_status=pending 은 refunded 아니므로 통과 — PaymentHistory 부재만으로 거절되지 않음.
    order = Order.objects.create(user=customer_user, name="x")
    response = ScanCodeApi(http_client=anon_client).list({"token": order.scancode_token})
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_scancode_opr_token_returns_order_product(anon_client, order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    response = ScanCodeApi(http_client=anon_client).list({"token": opr.scancode_token})
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_scancode_opr_token_with_invalid_salt_rejects(anon_client, order_factory):
    completed_order = order_factory(status="completed")
    opr = completed_order.products.first()
    # token 의 salt 부분 변조 — from_scancode_token 이 None 반환 → 403.
    tampered = opr.scancode_token[:-1] + ("A" if opr.scancode_token[-1] != "A" else "B")
    response = ScanCodeApi(http_client=anon_client).list({"token": tampered})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_scancode_user_token_returns_403_when_user_does_not_exist(anon_client):
    token = f"user:{shortuuid.encode(uuid.uuid4())}:fakesalt"
    response = ScanCodeApi(http_client=anon_client).list({"token": token})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_scancode_order_token_rejects_soft_deleted_order(anon_client, order_factory):
    # soft-deleted Order 의 scancode 가 유효하면 안 됨 — from_short_id 가 filter_active() 로 제외.
    order = order_factory(status="completed")
    token = order.scancode_token  # delete 전에 cache
    order.delete()
    response = ScanCodeApi(http_client=anon_client).list({"token": token})
    assert response.status_code == HTTP_404_NOT_FOUND  # refunded 와 동일 not-found 경로.


@pytest.mark.django_db
def test_scancode_opr_token_rejects_soft_deleted_opr(anon_client, order_factory):
    order = order_factory(status="completed")
    opr = order.products.first()
    token = opr.scancode_token
    opr.delete()
    response = ScanCodeApi(http_client=anon_client).list({"token": token})
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_scancode_order_token_returns_404_when_order_does_not_exist(anon_client):
    token = f"order:{shortuuid.encode(uuid.uuid4())}:fakesalt"
    response = ScanCodeApi(http_client=anon_client).list({"token": token})
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_scancode_pages_render_qr_with_full_token(anon_client, customer_user, order_factory):
    # QR 에 salt 없는 `prefix:short_id` 가 들어가면 등록 데스크 스캔이 전부 거절된다.
    order = order_factory(status="completed")
    for token in (customer_user.scancode_token, order.scancode_token, order.products.first().scancode_token):
        response = ScanCodeApi(http_client=anon_client).list({"token": token})
        assert response.status_code == HTTP_200_OK
        assert f'text: "{token}"' in response.content.decode()


@pytest.mark.django_db
def test_scancode_token_issued_with_rotated_out_salt_still_verifies(anon_client, order_factory, monkeypatch):
    order = order_factory(status="completed")

    monkeypatch.setattr(settings.SHOP, "order_scancode_salts", ["old_salt"])
    old_token = Order.objects.get(id=order.id).scancode_token  # cached_property 라 매번 새로 조회.

    monkeypatch.setattr(settings.SHOP, "order_scancode_salts", ["new_salt", "old_salt"])
    new_token = Order.objects.get(id=order.id).scancode_token
    assert new_token != old_token
    assert ScanCodeApi(http_client=anon_client).list({"token": old_token}).status_code == HTTP_200_OK
    assert ScanCodeApi(http_client=anon_client).list({"token": new_token}).status_code == HTTP_200_OK


@pytest.mark.django_db
def test_scancode_token_rejected_after_old_salt_removed(anon_client, order_factory, monkeypatch):
    order = order_factory(status="completed")

    monkeypatch.setattr(settings.SHOP, "order_scancode_salts", ["old_salt"])
    old_token = Order.objects.get(id=order.id).scancode_token

    monkeypatch.setattr(settings.SHOP, "order_scancode_salts", ["new_salt"])
    assert ScanCodeApi(http_client=anon_client).list({"token": old_token}).status_code == HTTP_404_NOT_FOUND
