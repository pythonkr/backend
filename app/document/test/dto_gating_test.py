import pytest
from document.issuable import IssuableMixin
from shop.order.models import Order, OrderProductRelation
from shop.order.serializers.dto import OrderProductRelationDto


def _certificate_status(opr: OrderProductRelation) -> str:
    return OrderProductRelationDto(opr).data["certificate_status"]


@pytest.mark.django_db
def test_certificate_status_issuable_for_used_ticket(certificate_issuable_opr: OrderProductRelation):
    assert _certificate_status(certificate_issuable_opr) == IssuableMixin.DocumentStatus.issuable


@pytest.mark.django_db
def test_certificate_status_issued_after_issue(certificate_issuable_opr: OrderProductRelation):
    certificate_issuable_opr.get_or_issue_document()
    assert _certificate_status(certificate_issuable_opr) == IssuableMixin.DocumentStatus.issued


@pytest.mark.django_db
def test_certificate_status_revoked_after_revoke(certificate_issuable_opr: OrderProductRelation):
    certificate_issuable_opr.get_or_issue_document().revoke()
    assert _certificate_status(certificate_issuable_opr) == IssuableMixin.DocumentStatus.revoked


@pytest.mark.django_db
def test_certificate_status_not_issuable_when_status_not_used(order_factory):
    order = order_factory(status="completed")  # OPR status=paid
    opr = order.products.select_related("product__category").get()
    assert _certificate_status(opr) == IssuableMixin.DocumentStatus.not_issuable


@pytest.mark.django_db
def test_certificate_status_not_issuable_when_not_ticket(used_ticket_opr: OrderProductRelation):
    used_ticket_opr.product.category.is_ticket = False
    used_ticket_opr.product.category.save()
    assert _certificate_status(used_ticket_opr) == IssuableMixin.DocumentStatus.not_issuable


@pytest.mark.django_db
def test_certificate_status_prefetched_without_extra_query(certificate_issuable_opr, django_assert_num_queries):
    # for_dto_response 의 issued_documents prefetch 로 상품별 document_status 가 추가 쿼리를 내지 않아야 함.
    certificate_issuable_opr.get_or_issue_document()
    order = Order.objects.for_dto_response().get(id=certificate_issuable_opr.order_id)
    with django_assert_num_queries(0):
        assert [p.document_status for p in order.active_products] == [IssuableMixin.DocumentStatus.issued]
