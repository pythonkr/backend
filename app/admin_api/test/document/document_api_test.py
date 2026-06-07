import pytest
from admin_api.test.helpers import DocumentTemplatesAdminApi, IssuedDocumentsAdminApi
from document.models import DocumentTemplate
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_issued_document_list_requires_superuser(customer_client, anon_client):
    assert IssuedDocumentsAdminApi(http_client=customer_client).list().status_code == HTTP_403_FORBIDDEN
    assert IssuedDocumentsAdminApi(http_client=anon_client).list().status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_issued_document_list_returns_documents(api_client, issued_document):
    response = IssuedDocumentsAdminApi(http_client=api_client).list()
    assert response.status_code == HTTP_200_OK
    row = next(r for r in response.json()["results"] if r["id"] == str(issued_document.id))
    assert row["issuable"] == {
        "app_label": issued_document.issuable._meta.app_label,
        "db_table": issued_document.issuable._meta.db_table,
        "id": str(issued_document.issuable.id),
        "label": str(issued_document.issuable),
    }


@pytest.mark.django_db
def test_revoke_marks_document_revoked(api_client, issued_document):
    response = IssuedDocumentsAdminApi(http_client=api_client).revoke(issued_document.id)
    assert response.status_code == HTTP_200_OK
    assert response.json()["revoked_at"] is not None
    issued_document.refresh_from_db()
    assert issued_document.revoked_at is not None
    assert issued_document.revoked_by is not None


@pytest.mark.django_db
def test_revoke_is_idempotent(api_client, issued_document):
    api = IssuedDocumentsAdminApi(http_client=api_client)
    first = api.revoke(issued_document.id)
    second = api.revoke(issued_document.id)
    assert first.status_code == second.status_code == HTTP_200_OK
    assert second.json()["revoked_at"] is not None


@pytest.mark.django_db
def test_document_template_create_and_list(api_client):
    # 타입당 활성 1개 제약 — 기존 활성 템플릿을 삭제(soft-delete) 후 새로 생성.
    DocumentTemplate.objects.filter_active().delete()
    api = DocumentTemplatesAdminApi(http_client=api_client)
    create = api.create({"document_type": "confirmation_of_participation", "body": "<p>new</p>"})
    assert create.status_code == HTTP_201_CREATED

    listed = api.list()
    assert listed.status_code == HTTP_200_OK
    bodies = {row["body"] for row in listed.json()["results"]}
    assert "<p>new</p>" in bodies


@pytest.mark.django_db
def test_document_template_create_rejects_duplicate_active_type(api_client, certificate_template):
    # 활성 템플릿이 이미 있는데 같은 타입을 또 생성하면 IntegrityError(500) 가 아니라 400.
    response = DocumentTemplatesAdminApi(http_client=api_client).create(
        {"document_type": certificate_template.document_type, "body": "<p>dup</p>"}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "document_type" in {error["attr"] for error in response.json()["errors"]}


@pytest.mark.django_db
def test_document_template_update_allowed_when_unused(api_client, certificate_template):
    # 발급 전(미사용) 템플릿은 자유롭게 수정 가능.
    response = DocumentTemplatesAdminApi(http_client=api_client).update(certificate_template.id, {"body": "tweak"})
    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_document_template_update_blocked_when_used(api_client, issued_document):
    # 발급에 사용된 템플릿은 불변 — 수정 시 이미 발급된 문서가 바뀌므로 400.
    response = DocumentTemplatesAdminApi(http_client=api_client).update(
        issued_document.template.id, {"body": "<p>changed</p>"}
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
