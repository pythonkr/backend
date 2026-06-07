import pytest
from document.models import IssuedDocument
from document.test.helpers import DocumentApi
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_410_GONE,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from shop.order.models import OrderProductRelation


@pytest.mark.django_db
def test_download_requires_authentication(anon_client, issued_document):
    assert DocumentApi(http_client=anon_client).download(issued_document.id).status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_download_returns_pdf_for_owner(customer_client, issued_document, _fake_pdf):
    response = DocumentApi(http_client=customer_client).download(issued_document.id)
    assert response.status_code == HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment; filename*=UTF-8''")
    assert response.content == b"%PDF-1.7 fake"


@pytest.mark.django_db
def test_download_never_issues_document(customer_client, issued_document, _fake_pdf):
    # 다운로드는 순수 조회 — 호출해도 발급본 수가 늘지 않는다.
    api = DocumentApi(http_client=customer_client)
    api.download(issued_document.id)
    api.download(issued_document.id)
    assert IssuedDocument.objects.for_issuable(issued_document.issuable).count() == 1


@pytest.mark.django_db
def test_download_forbidden_for_non_owner(other_client, issued_document, _fake_pdf):
    assert DocumentApi(http_client=other_client).download(issued_document.id).status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_download_404_when_opr_no_longer_valid(customer_client, issued_document, _fake_pdf):
    # 발급 후 OPR 이 사용취소(환불)되면 더 이상 다운로드 불가.
    issued_document.issuable.status = OrderProductRelation.OrderProductStatus.refunded
    issued_document.issuable.save()
    assert DocumentApi(http_client=customer_client).download(issued_document.id).status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_download_410_when_revoked(customer_client, issued_document, _fake_pdf):
    issued_document.revoke()
    assert DocumentApi(http_client=customer_client).download(issued_document.id).status_code == HTTP_410_GONE


@pytest.mark.django_db
def test_download_503_when_rendering_unavailable(customer_client, issued_document):
    # _fake_pdf 안 씀 — autouse(_no_real_weasyprint)가 HTML 을 raise 로 강제 → render_pdf RuntimeError → 503.
    response = DocumentApi(http_client=customer_client).download(issued_document.id)
    assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE
