"""SingleProductCart 의 동시 webhook race condition invariant 검증.

PortOne 이 거의 동시에 같은 cart 에 대해 webhook 두 번을 보낸 경우 (예: 결제 완료 + retry),
`PortOneV1WebhookRequestSerializer._lock_or_promote_order` 의 `select_for_update` 기반 lock 이
정확히 한 번만 cart→Order 승격 + PaymentHistory 생성이 이뤄지도록 보장하는지 검증한다.

테스트는 `transaction=True` 마크 + `threading.Barrier` 로 두 스레드를 동기 진입시킴.
"""

import threading

import pytest
from django.db import connections
from shop.order.models import Order, SingleProductCart
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.payment_history.serializers import PortOneV1WebhookRequestSerializer
from shop.test.helpers import make_portone_payment_info, make_webhook_payload


@pytest.mark.django_db(transaction=True)
def test_concurrent_webhooks_for_same_cart_create_exactly_one_payment_history(
    single_product_cart, mock_portone_find_payment_info
):
    cart_id = single_product_cart.id
    expected_price = single_product_cart.first_paid_price
    single_product_cart.prepare_payment()
    merchant_uid = single_product_cart.merchant_uid
    mock_portone_find_payment_info.return_value = make_portone_payment_info(order=single_product_cart)

    barrier = threading.Barrier(2)
    results: list[tuple[str, object]] = []
    results_lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            serializer = PortOneV1WebhookRequestSerializer(data=make_webhook_payload(merchant_uid=merchant_uid))
            # 두 스레드 모두 is_valid 단계에서는 cart 가 보임 (cached_property 캐시) — race 는 create() 진입 시점.
            if serializer.is_valid():
                serializer.save()
                outcome: tuple[str, object] = ("ok", None)
            else:
                outcome = ("validation_error", serializer.errors)
        except Exception as exc:
            outcome = ("exception", exc)
        finally:
            connections.close_all()
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # Invariant 1: 정확히 1번만 PaymentHistory(completed) 가 생성됨.
    completed_phs = PaymentHistory.objects.filter(order_id=cart_id, status=PaymentHistoryStatus.completed)
    assert completed_phs.count() == 1
    assert completed_phs.get().price == expected_price

    # Invariant 2: cart 는 정확히 한 번만 to_order() 호출되어 Order 로 승격됨.
    assert Order.objects.filter(id=cart_id).count() == 1
    assert not SingleProductCart.objects.filter(id=cart_id).exists()

    # Invariant 3: 두 스레드 중 정확히 하나는 성공, 다른 하나는 거절 (state machine illegal_transition 또는 forgery).
    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1
    assert len(outcomes) == 2
    losing_outcome = next(r for r in results if r[0] != "ok")
    # 거절 사유는 timing 에 따라 다를 수 있지만 — 어쨌든 두 번째 webhook 은 명시적으로 실패해야 함.
    assert losing_outcome[0] in {"validation_error", "exception"}
