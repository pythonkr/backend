from __future__ import annotations

from datetime import datetime
from logging import getLogger
from traceback import format_exception
from typing import Any, Literal

from django.conf import settings
from httpx import Client
from httpx._types import TimeoutTypes

from .serializers import NHNKCPReceiptContext, PortOneV1ResponseSerializer

logger = getLogger(__name__)

DEFAULT_TIMEOUT = 5
RequestMethodType = Literal["GET", "OPTIONS", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


class PortOneException(Exception):
    pass


class PortOneExceptionGroup(ExceptionGroup):
    pass


class PortOneClient:
    def __init__(self, timeout: TimeoutTypes = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        # httpx.Client 는 settings 를 참조하므로 첫 요청 시점까지 생성을 지연한다.
        if self._client is None:
            self._client = Client(base_url=settings.PORTONE.api_url, timeout=self._timeout)
        return self._client

    @property
    def _access_token(self) -> str:
        response = self.client.post(
            url="/users/getToken", json={"imp_key": settings.PORTONE.imp_key, "imp_secret": settings.PORTONE.imp_secret}
        )

        try:
            resp_serializer = PortOneV1ResponseSerializer.from_response(response)
            resp_serializer.is_valid(raise_exception=True)

            if not (access_token := resp_serializer.validated_data["response"]["access_token"]):
                raise ValueError("PortOne access_token 값이 존재하지 않습니다.")

            return access_token

        except Exception as e:
            logger.error(format_exception(e))
            raise PortOneException("PortOne AccessToken 획득에 실패했습니다.") from e

    def _request(
        self,
        method: RequestMethodType,
        route: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        action_desc: str = "UNDEFINED_ACTION",
    ) -> dict:
        response = self.client.request(
            method=method,
            url=route,
            json=json,
            headers={"Authorization": self._access_token, "Content-Type": "application/json"} | (headers or {}),
            timeout=timeout,
        )

        try:
            resp_serializer = PortOneV1ResponseSerializer.from_response(response)
            resp_serializer.is_valid(raise_exception=True)
            return resp_serializer.validated_data
        except Exception as e:
            logger.error(format_exception(e))
            raise PortOneException(f"PortOne API 요청이 실패했습니다. [{action_desc}]") from e

    def register_prepared_payment(self, merchant_id: str, price: int) -> dict:
        """결제 금액 사전 등록 요청
        Args:
            merchant_id (str): 결제 번호
            price (int): 결제 금액
        Returns:
            dict: 결제 사전 등록 응답
        """
        return self._request(
            method="POST",
            route="/payments/prepare",
            json={"merchant_uid": merchant_id, "amount": price},
            action_desc="결제 금액 사전 등록",
        )

    def update_prepared_payment(self, merchant_id: str, price: int) -> dict:
        """결제 금액 사전 수정 요청
        Args:
            merchant_id (str): 결제 번호
            price (int): 수정된 결제 금액
        Returns:
            dict: 결제 사전 수정 응답
        """
        return self._request(
            method="PUT",
            route="/payments/prepare",
            json={"merchant_uid": merchant_id, "amount": price},
            action_desc="결제 금액 사전 수정",
        )

    def register_or_update_prepared_payment(self, merchant_id: str, price: int) -> dict:
        """결제 금액 사전 등록 또는 수정 요청
        Args:
            merchant_id (str): 결제 번호
            price (int): 결제 금액
        Returns:
            dict: 결제 사전 등록 또는 수정 응답
        """
        try:
            return self.register_prepared_payment(merchant_id, price)
        except PortOneException as e1:
            try:
                return self.update_prepared_payment(merchant_id, price)
            except PortOneException as e2:
                raise PortOneExceptionGroup(f"결제금액 사전 등록 또는 수정에 실패했습니다. {merchant_id=}", [e1, e2])

    def find_payment_info(self, imp_uid: str) -> dict:
        if payment_data := self._request(method="GET", route=f"/payments/{imp_uid}").get("response"):
            return payment_data

        raise PortOneException(f"결제 정보를 찾을 수 없습니다. {imp_uid=}")

    def req_cancel_payment(
        self, merchant_id: str, refund_request_price: int, current_leftover_price: int, reason: str | None = None
    ) -> dict:
        """결제 환불 요청
        Args:
            merchant_id (str): 결제 번호
            refund_request_price (int): 환불 요청 금액
            current_leftover_price (int): 현재 환불 가능한 남은 금액
            reason (str | None): 환불 사유
        Returns:
            dict: 결제 사전 등록 또는 수정 응답
        """
        request_dto = {
            "merchant_uid": merchant_id,
            "amount": refund_request_price,
            "checksum": current_leftover_price,
            "reason": reason,
        }

        return self._request(
            method="POST",
            route="/payments/cancel",
            json={k: v for k, v in request_dto.items() if v},
            action_desc="환불 요청",
        )

    def get_kcp_receipt_search_data(self, imp_uid: str) -> NHNKCPReceiptContext:
        """KCP 영수증 조회 시 필요 데이터"""
        payment_data = self.find_payment_info(imp_uid)
        return NHNKCPReceiptContext(
            instance={
                "cmd": "card_bill",
                "order_no": imp_uid,
                "tno": payment_data["pg_tid"],
                "trade_mony": payment_data["amount"],
                "req_dt": datetime.now(),
            }
        )


portone_client = PortOneClient()
