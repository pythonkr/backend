import pytest
from document.test.helpers import DocumentApi
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_410_GONE
from shop.order.models import OrderProductRelation


@pytest.mark.django_db
def test_verify_valid_shows_participant_info(anon_client, issued_document):
    response = DocumentApi(http_client=anon_client).verify(issued_document.verify_token)
    assert response.status_code == HTTP_200_OK
    assert response.data["fields"]["참가자명"] == "홍길동"
    assert response.data["document_number"] == issued_document.document_number


@pytest.mark.django_db
def test_verify_revoked(anon_client, issued_document):
    issued_document.revoke()
    response = DocumentApi(http_client=anon_client).verify(issued_document.verify_token)
    assert response.status_code == HTTP_410_GONE
    assert "반려" in response.data["message"]
    assert "fields" not in response.data


@pytest.mark.django_db
def test_verify_invalid_when_opr_not_used(anon_client, issued_document):
    OrderProductRelation.objects.filter(id=issued_document.issuable_object_id).update(
        status=OrderProductRelation.OrderProductStatus.refunded
    )
    response = DocumentApi(http_client=anon_client).verify(issued_document.verify_token)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "유효하지 않습니다" in response.data["message"]
    assert "fields" not in response.data


@pytest.mark.django_db
def test_verify_404_for_unknown_token(anon_client):
    response = DocumentApi(http_client=anon_client).verify("cert:unknownshortid:badsalt")
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_verify_404_for_malformed_token(anon_client):
    response = DocumentApi(http_client=anon_client).verify("garbage")
    assert response.status_code == HTTP_404_NOT_FOUND
