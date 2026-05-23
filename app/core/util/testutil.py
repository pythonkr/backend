import json
from dataclasses import dataclass
from typing import ClassVar

from django.urls import reverse
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient


def to_json(data) -> dict | list:
    """DRF serializer.data → JSON round-trip 결과. response.json() 과 동일한 형식 비교용.

    `.data` 가 raw datetime / UUID / 등 native 값을 들고 있을 때 JSONRenderer 가 string 직렬화 적용한 결과.
    """
    return json.loads(JSONRenderer().render(data))


@dataclass
class ModelApiFixture:
    """ViewSet 기본 CRUD URL + HTTP method dispatch 헬퍼. 서브클래스에서 `name` 으로 router basename 지정.

    사용:
        class OrdersApi(ModelApiFixture):
            name = "v1:orders"

        api = OrdersApi(http_client=customer_client)
        response = api.list()
        response = api.retrieve(order.id)
    """

    http_client: APIClient
    name: ClassVar[str] = ""

    def list(self, params=None):
        return self.http_client.get(reverse(f"{self.name}-list"), params)

    def create(self, data=None):
        return self.http_client.post(reverse(f"{self.name}-list"), data, format="json")

    def retrieve(self, pk, params=None):
        return self.http_client.get(reverse(f"{self.name}-detail", args=(pk,)), params)

    def update(self, pk, data=None):
        return self.http_client.patch(reverse(f"{self.name}-detail", args=(pk,)), data, format="json")

    def delete(self, pk):
        return self.http_client.delete(reverse(f"{self.name}-detail", args=(pk,)))


def errors_payload(errors: dict | list) -> dict | list:
    """DRF `serializer.errors` / `ValidationError.detail` 을 plain dict / list 로 변환.

    `ErrorDetail` 은 `str` subclass 라 `__eq__` 가 string 만 비교 — code 변경이 dict equality 로 잡히지 않는다.
    본 헬퍼로 `{detail, code}` 평탄화 후 비교하면 message + code 둘 다 catch.
    """

    def _err(e) -> dict:
        return {"detail": str(e), "code": e.code}

    if isinstance(errors, list):
        return [_err(e) for e in errors]
    return {k: [_err(e) for e in v] for k, v in errors.items()}


def pk_does_not_exist_error(pk) -> dict:
    """`PrimaryKeyRelatedField` 의 `does_not_exist` 에러 페이로드 — queryset 필터 boundary 테스트용."""
    return {"detail": f'유효하지 않은 pk "{pk}" - 객체가 존재하지 않습니다.', "code": "does_not_exist"}
