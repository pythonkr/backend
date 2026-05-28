from __future__ import annotations

from datetime import datetime, timedelta
from logging import getLogger
from time import time
from traceback import format_exception
from typing import Any, Literal

from django.conf import settings
from httpx import Client
from httpx._types import TimeoutTypes

from .serializers import NHNKCPReceiptContext, PortOneV1ResponseSerializer

logger = getLogger(__name__)

DEFAULT_TIMEOUT = 5
# PortOne v1 access_token 의 공식 TTL 은 발행 시점 +30분 (developers.portone.io 명시).
# 응답에 `expired_at` (unix epoch sec) 가 포함되며, 만료 직전 재발급 race 를 막기 위한 안전 마진.
TOKEN_REFRESH_MARGIN = timedelta(seconds=30)
# `expired_at` 가 응답에 누락된 비정상 케이스의 보수적 fallback (공식 TTL 30분보다 짧게).
TOKEN_FALLBACK_TTL = timedelta(minutes=5)
RequestMethodType = Literal["GET", "OPTIONS", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


class PortOneException(Exception):
    pass


class PortOneExceptionGroup(ExceptionGroup):
    pass


class PortOneClient:
    def __init__(self, timeout: TimeoutTypes = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._client: Client | None = None
        self._cached_token: str | None = None
        self._cached_token_expires_at: float = 0.0

    @property
    def client(self) -> Client:
        # httpx.Client 는 settings 를 참조하므로 첫 요청 시점까지 생성을 지연한다.
        if self._client is None:
            self._client = Client(base_url=settings.PORTONE.api_url, timeout=self._timeout)
        return self._client

    @property
    def _access_token(self) -> str:
        # 만료 직전 안전 마진까지는 캐시 재사용 (PortOne 토큰 TTL 30분).
        if self._cached_token and time() < self._cached_token_expires_at - TOKEN_REFRESH_MARGIN.total_seconds():
            return self._cached_token

        response = self.client.post(
            url="/users/getToken", json={"imp_key": settings.PORTONE.imp_key, "imp_secret": settings.PORTONE.imp_secret}
        )

        try:
            resp_serializer = PortOneV1ResponseSerializer.from_response(response)
            resp_serializer.is_valid(raise_exception=True)

            resp = resp_serializer.validated_data["response"]
            if not (access_token := resp.get("access_token")):
                raise ValueError("PortOne access_token 값이 존재하지 않습니다.")

        except Exception as e:
            logger.error(format_exception(e))
            raise PortOneException("PortOne AccessToken 획득에 실패했습니다.") from e

        self._cached_token = access_token
        self._cached_token_expires_at = float(resp.get("expired_at") or (time() + TOKEN_FALLBACK_TTL.total_seconds()))
        return access_token

    def _request(
        self,
        method: RequestMethodType,
        route: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        action_desc: str = "UNDEFINED_ACTION",
    ) -> dict:
        response = self.client.request(
            method=method,
            url=route,
            json=json,
            params=params,
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
        if payment_data := self._request(
            method="GET",
            route=f"/payments/{imp_uid}",
            params={"include_sandbox": "true"},
        ).get("response"):
            return payment_data

        raise PortOneException(f"결제 정보를 찾을 수 없습니다. {imp_uid=}")

    def req_cancel_payment(
        self,
        imp_id: str,
        refund_request_price: int | float,
        current_leftover_price: int | float,
        reason: str | None = None,
    ) -> dict:
        """결제 환불 요청
        Args:
            imp_id (str): 포트원 거래고유번호
            refund_request_price (int | float): 환불 요청 금액
            current_leftover_price (int | float): 현재 환불 가능한 남은 금액
            reason (str | None): 환불 사유
        Returns:
            dict: 결제 사전 등록 또는 수정 응답
        """
        request_dto = {
            "imp_uid": imp_id,
            "amount": refund_request_price,
            "checksum": current_leftover_price,
            "reason": reason,
        }

        return self._request(
            method="POST",
            route="/payments/cancel",
            json={k: v for k, v in request_dto.items() if v is not None},
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
