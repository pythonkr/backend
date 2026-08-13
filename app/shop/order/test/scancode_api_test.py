import uuid

import pytest
import shortuuid
from core.const.scancode import SCANCODE_ERROR_GUIDE, SCANCODE_MESSAGES
from django.conf import settings
from django.urls import reverse
from django.utils.html import escape
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


@pytest.mark.django_db
def test_scancode_error_page_shows_both_languages_and_guide(anon_client, order_factory):
    order = order_factory(status="completed")
    tampered = order.scancode_token[:-1] + "A"

    response = anon_client.get(reverse("v1:scancode-list"), {"token": tampered}, HTTP_ACCEPT_LANGUAGE="ko-KR,ko;q=0.9")
    body = response.content.decode()
    assert response.status_code == HTTP_404_NOT_FOUND
    assert escape(SCANCODE_MESSAGES["order_not_found"]["ko"]) in body
    assert escape(SCANCODE_MESSAGES["order_not_found"]["en"]) in body  # 보조 언어 병기.
    assert escape(SCANCODE_ERROR_GUIDE["ko"]) in body


@pytest.mark.django_db
def test_scancode_error_page_is_english_for_english_client(anon_client, order_factory):
    order = order_factory(status="completed")
    tampered = order.scancode_token[:-1] + "A"

    response = anon_client.get(reverse("v1:scancode-list"), {"token": tampered}, HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    body = response.content.decode()
    assert '<html lang="en">' in body
    assert f"<h4>\n  {escape(SCANCODE_MESSAGES['order_not_found']['en'])}\n</h4>" in body  # 영어가 주 문구.
    assert escape(SCANCODE_ERROR_GUIDE["en"]) in body


@pytest.mark.django_db
def test_scancode_renders_html_even_when_client_asks_for_json(anon_client, order_factory):
    # 일부 QR 스캐너 인앱 브라우저의 Accept 헤더 때문에 406 이 나가면 안 된다.
    order = order_factory(status="completed")

    ok = anon_client.get(reverse("v1:scancode-list"), {"token": order.scancode_token}, HTTP_ACCEPT="application/json")
    assert ok.status_code == HTTP_200_OK
    assert ok["Content-Type"].startswith("text/html")

    tampered = order.scancode_token[:-1] + "A"
    error = anon_client.get(reverse("v1:scancode-list"), {"token": tampered}, HTTP_ACCEPT="application/json")
    assert error.status_code == HTTP_404_NOT_FOUND
    assert SCANCODE_MESSAGES["order_not_found"]["ko"] in error.content.decode()
