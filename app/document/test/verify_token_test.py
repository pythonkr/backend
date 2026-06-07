import pytest
from document.models import IssuedDocument
from shop.order.models import OrderProductRelation


@pytest.mark.django_db
def test_from_verify_token_round_trip(issued_document):
    found = IssuedDocument.objects.from_verify_token(issued_document.verify_token)
    assert found.id == issued_document.id


@pytest.mark.django_db
def test_from_verify_token_rejects_tampered_salt(issued_document):
    prefix, short_id, _salt = issued_document.verify_token.split(":")
    assert IssuedDocument.objects.from_verify_token(f"{prefix}:{short_id}:tampered") is None


@pytest.mark.django_db
def test_from_verify_token_rejects_bad_format(issued_document):
    assert IssuedDocument.objects.from_verify_token("garbage") is None
    assert IssuedDocument.objects.from_verify_token("") is None


@pytest.mark.django_db
def test_from_verify_token_excludes_soft_deleted(issued_document):
    token = issued_document.verify_token
    issued_document.delete()  # soft delete → "존재하지 않음"
    assert IssuedDocument.objects.from_verify_token(token) is None


@pytest.mark.django_db
def test_from_verify_token_still_finds_revoked(issued_document):
    # revoked 문서는 검증 페이지가 "취소됨" 으로 표시해야 하므로 조회는 성공해야 한다.
    token = issued_document.verify_token
    issued_document.revoke()
    found = IssuedDocument.objects.from_verify_token(token)
    assert found is not None
    assert found.revoked_at is not None


@pytest.mark.django_db
def test_scancode_token_is_not_a_valid_verify_token(used_ticket_opr: OrderProductRelation):
    # 공개 검증 QR(cert) 과 scancode(opr) 토큰은 prefix/salt 가 분리돼 호환되지 않는다.
    assert IssuedDocument.objects.from_verify_token(used_ticket_opr.scancode_token) is None
