from unittest.mock import patch

import pytest


@pytest.fixture
def mocked_on_commit():
    # test transaction 은 rollback 되므로 on_commit callback 이 실제로 fire 안 됨 — 등록만 검증.
    with patch("shop.payment_history.serializers.transaction.on_commit") as mocked:
        yield mocked
