import pytest
from shop.payment_history.models import (
    LEGAL_PAYMENT_STATUS_TRANSITIONS,
    PURCHASED_STATUSES,
    REFUNDABLE_STATUSES,
    PaymentHistoryStatus,
    is_legal_payment_status_transition,
)


@pytest.mark.parametrize(
    ("current", "next_"),
    [
        (PaymentHistoryStatus.pending, PaymentHistoryStatus.completed),
        (PaymentHistoryStatus.completed, PaymentHistoryStatus.partial_refunded),
        (PaymentHistoryStatus.completed, PaymentHistoryStatus.refunded),
        (PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.partial_refunded),  # 추가 부분환불
        (PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.refunded),
    ],
)
def test_legal_transitions_are_allowed(current: PaymentHistoryStatus, next_: PaymentHistoryStatus) -> None:
    assert is_legal_payment_status_transition(current, next_) is True


@pytest.mark.parametrize(
    ("current", "next_"),
    [
        # pending 에서 결제 이외의 상태로 점프 금지 (결제 안 한 주문 환불 차단)
        (PaymentHistoryStatus.pending, PaymentHistoryStatus.pending),
        (PaymentHistoryStatus.pending, PaymentHistoryStatus.partial_refunded),
        (PaymentHistoryStatus.pending, PaymentHistoryStatus.refunded),
        # completed 자기복제 금지 (중복 웹훅으로 두 번 paid 처리되는 시나리오 차단)
        (PaymentHistoryStatus.completed, PaymentHistoryStatus.pending),
        (PaymentHistoryStatus.completed, PaymentHistoryStatus.completed),
        # partial_refunded 에서 결제 상태로 되돌리기 금지
        (PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.pending),
        (PaymentHistoryStatus.partial_refunded, PaymentHistoryStatus.completed),
        # refunded 는 terminal — 어떤 전이도 불가
        (PaymentHistoryStatus.refunded, PaymentHistoryStatus.pending),
        (PaymentHistoryStatus.refunded, PaymentHistoryStatus.completed),
        (PaymentHistoryStatus.refunded, PaymentHistoryStatus.partial_refunded),
        (PaymentHistoryStatus.refunded, PaymentHistoryStatus.refunded),
    ],
)
def test_illegal_transitions_are_rejected(current: PaymentHistoryStatus, next_: PaymentHistoryStatus) -> None:
    assert is_legal_payment_status_transition(current, next_) is False


def test_refundable_statuses_contains_only_completed_and_partial_refunded() -> None:
    # 개인 후원자 목록 조회 API가 이 상수에 의존 — pending 이 들어가면 결제 안 한 주문에도 후원자 이름이 노출될 수 있음.
    assert REFUNDABLE_STATUSES == {PaymentHistoryStatus.completed, PaymentHistoryStatus.partial_refunded}


def test_purchased_statuses_is_refundable_plus_refunded() -> None:
    # "결제됨" 상태의 정의 — REFUNDABLE_STATUSES ∪ {refunded}.
    # pending 이 PURCHASED_STATUSES 에 섞이면 cart 가 결제된 주문으로 잘못 분류된다.
    assert PURCHASED_STATUSES == REFUNDABLE_STATUSES | {PaymentHistoryStatus.refunded}
    assert PaymentHistoryStatus.pending not in PURCHASED_STATUSES


def test_legal_transitions_graph_covers_every_enum_member() -> None:
    # 새 상태 enum 추가 시 전이 정의를 빠뜨리면 함수가 조용히 False 만 반환하므로 그래프의 key set 과 enum 멤버 set 이 일치하는지 직접 단언.
    assert LEGAL_PAYMENT_STATUS_TRANSITIONS.keys() == set(PaymentHistoryStatus)
