import pytest
from document.models import DocumentTemplate, IssuedDocument
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_410_GONE, HTTP_503_SERVICE_UNAVAILABLE
from shop.test.helpers import OrderProductsApi


@pytest.mark.django_db
def test_issue_certificate_returns_download_url(customer_client, certificate_issuable_opr):
    response = OrderProductsApi(http_client=customer_client).certificate(
        certificate_issuable_opr.order_id, certificate_issuable_opr.id
    )
    assert response.status_code == HTTP_200_OK
    document = IssuedDocument.objects.for_issuable(certificate_issuable_opr).get()
    assert str(document.id) in response.json()["download_url"]


@pytest.mark.django_db
def test_issue_certificate_is_idempotent(customer_client, certificate_issuable_opr):
    api = OrderProductsApi(http_client=customer_client)
    first = api.certificate(certificate_issuable_opr.order_id, certificate_issuable_opr.id)
    second = api.certificate(certificate_issuable_opr.order_id, certificate_issuable_opr.id)
    assert first.json()["download_url"] == second.json()["download_url"]
    assert IssuedDocument.objects.for_issuable(certificate_issuable_opr).count() == 1


@pytest.mark.django_db
def test_issue_certificate_404_when_not_issuable(customer_client, order_factory):
    # used 가 아닌 paid 상품 → 발급 가능 queryset 에서 빠져 404.
    order = order_factory(status="completed")
    opr = order.products.get()
    response = OrderProductsApi(http_client=customer_client).certificate(opr.order_id, opr.id)
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_issue_certificate_410_when_revoked(customer_client, certificate_issuable_opr):
    certificate_issuable_opr.get_or_issue_document().revoke()
    response = OrderProductsApi(http_client=customer_client).certificate(
        certificate_issuable_opr.order_id, certificate_issuable_opr.id
    )
    assert response.status_code == HTTP_410_GONE


@pytest.mark.django_db
def test_issue_certificate_rejects_other_user(other_client, certificate_issuable_opr):
    response = OrderProductsApi(http_client=other_client).certificate(
        certificate_issuable_opr.order_id, certificate_issuable_opr.id
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_issue_certificate_503_when_no_active_template(customer_client, certificate_issuable_opr):
    DocumentTemplate.objects.filter_active().delete()  # 활성 템플릿 제거 → get_active 가 DoesNotExist → 503
    response = OrderProductsApi(http_client=customer_client).certificate(
        certificate_issuable_opr.order_id, certificate_issuable_opr.id
    )
    assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE
