from __future__ import annotations

from base64 import b64encode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from httpx import Response
from rest_framework import serializers


class PortOneV1ResponseSerializer(serializers.Serializer):
    code = serializers.IntegerField(required=True)
    message = serializers.CharField(required=True, allow_blank=True, allow_null=True)
    response = serializers.DictField(required=True, allow_null=True)

    @classmethod
    def from_response(cls, response: Response) -> PortOneV1ResponseSerializer:
        return cls(data=response.raise_for_status().json())

    def validate_code(self, value: int) -> int:
        # PortOne API 응답 코드가 0이 아닌 경우는 문제가 있는 경우입니다.
        # https://developers.portone.io/docs/ko/auth/guide-2/readme?v=v1#step-04-%ED%99%98%EB%B6%88-%EA%B2%B0%EA%B3%BC-%EC%A0%80%EC%9E%A5%ED%95%98%EA%B8%B0
        if value != 0:
            raise serializers.ValidationError(f"PortOne API 응답 코드가 0이 아닙니다. {self.initial_data=}")
        return value


class NHNKCPReceiptContext(serializers.Serializer):
    cmd = serializers.ChoiceField(choices=["mcash_bill", "card_bill"], required=True)
    order_no = serializers.CharField(required=True, help_text="PortOne 주문ID (ex: imp_123456789012)")
    tno = serializers.CharField(required=True, help_text="KCP 주문ID (ex: 24902225098168)")
    trade_mony = serializers.IntegerField(required=True, help_text="First Paid Price")
    req_dt = serializers.DateTimeField(required=True, help_text="Request Datetime", format="%Y%m%d%H%M%S")

    def to_search_data(self) -> str:
        return "^".join(f"{k}={v}" for k, v in self.data.items())

    def to_kcp_signed_search_data(self, private_key: str, password: str) -> str:
        pem_private_key = load_pem_private_key(
            data=private_key.encode(),
            password=password.encode(),
            backend=default_backend(),
        )
        assert isinstance(pem_private_key, RSAPrivateKey)  # nosec: B101
        signed_data = pem_private_key.sign(
            self.to_search_data().encode(),
            padding=PKCS1v15(),
            algorithm=SHA256(),
        )
        return b64encode(signed_data).decode()
