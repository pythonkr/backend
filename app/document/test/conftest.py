import pytest
from document.models import DocumentTemplate, DocumentType, IssuedDocument

# document 발급 대상은 shop OPR 이므로 shop fixture(주문/클라이언트)를 재사용한다.
from shop.conftest import (  # noqa: F401
    anon_client,
    customer_client,
    customer_user,
    donation_product,
    order_factory,
    other_client,
    other_user,
    ticket_product,
    used_ticket_opr,
)
from shop.order.models import OrderProductRelation


@pytest.fixture(autouse=True)
def _no_real_weasyprint(monkeypatch):
    class _RaisingHTML:
        """테스트용 HTML stub — write_pdf 호출 시 항상 RuntimeError(실제 WeasyPrint 미사용)."""

        def __init__(self, *args, **kwargs) -> None:
            pass

        def write_pdf(self, *args, **kwargs) -> bytes:
            raise RuntimeError(
                "테스트에서는 WeasyPrint 를 호출하지 않습니다 — PDF 가 필요하면 _fake_pdf(=HTML mock) 를 쓰세요."
            )

    monkeypatch.setattr("document.models.HTML", _RaisingHTML)


@pytest.fixture
def _fake_pdf(monkeypatch):
    class _FakeHTML:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def write_pdf(self, *args, **kwargs) -> bytes:
            return b"%PDF-1.7 fake"

    monkeypatch.setattr("document.models.HTML", _FakeHTML)


@pytest.fixture
def certificate_template(db) -> DocumentTemplate:
    # 시드는 --reuse-db + transactional 테스트에서 보존되지 않으므로(첫 flush 미복원) 활성 템플릿을 직접 보장.
    return DocumentTemplate.objects.update_or_create(
        document_type=DocumentType.confirmation_of_participation,
        defaults={
            "body": (
                "<html><body><h1>참 가 확 인 서</h1>"
                "<p>{{ document_number }}</p><p>{{ participant_name }}</p>"
                '<img src="{{ qr_data_uri }}" /></body></html>'
            ),
        },
    )[0]


@pytest.fixture
def certificate_issuable_opr(certificate_template, request) -> OrderProductRelation:
    """활성 참가확인서 템플릿까지 보장된 발급 가능 OPR."""
    return request.getfixturevalue("used_ticket_opr")


@pytest.fixture
def issued_document(certificate_issuable_opr) -> IssuedDocument:
    return certificate_issuable_opr.get_or_issue_document()
