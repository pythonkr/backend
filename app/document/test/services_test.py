import pytest
from django.db import IntegrityError, transaction
from document.models import DocumentTemplate, IssuedDocument
from shop.order.models import OrderProductRelation


@pytest.mark.django_db
def test_build_document_context_freezes_participant_data(used_ticket_opr: OrderProductRelation):
    context = used_ticket_opr.build_document_context()
    assert context["participant_name"] == "홍길동"
    assert "event_name" in context
    assert "options" not in context


@pytest.mark.django_db
def test_get_or_issue_document_is_idempotent(certificate_issuable_opr: OrderProductRelation):
    first = certificate_issuable_opr.get_or_issue_document()
    second = certificate_issuable_opr.get_or_issue_document()
    assert first.id == second.id
    assert IssuedDocument.objects.for_issuable(certificate_issuable_opr).count() == 1


@pytest.mark.django_db
def test_only_one_active_document_per_issuable(certificate_issuable_opr: OrderProductRelation):
    certificate_issuable_opr.issue_document()
    with pytest.raises(IntegrityError), transaction.atomic():
        certificate_issuable_opr.issue_document()  # 부분 unique constraint 가 중복 활성 문서 차단


@pytest.mark.django_db
def test_get_or_issue_document_blocked_after_revoke(certificate_issuable_opr: OrderProductRelation):
    document = certificate_issuable_opr.get_or_issue_document()
    document.revoke()
    with pytest.raises(IssuedDocument.RevokedError):
        certificate_issuable_opr.get_or_issue_document()


@pytest.mark.django_db
def test_issue_without_active_template_raises(certificate_issuable_opr: OrderProductRelation):
    DocumentTemplate.objects.all().delete()  # 활성 템플릿 soft-delete → get_active 가 DoesNotExist
    with pytest.raises(DocumentTemplate.DoesNotExist):
        certificate_issuable_opr.get_or_issue_document()
