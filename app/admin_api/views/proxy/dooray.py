from __future__ import annotations

import re

import httpx
from core.authz import IsSuperUser
from core.external_apis.nhn_cloud.dooray import DoorayError, nhn_cloud_dooray_client
from rest_framework import request as drf_request
from rest_framework import response, status
from rest_framework.views import APIView

_ALLOWED_PATH = re.compile(r"^/(?:project/v1/|common/v1/members(?:/|$))")


class DoorayProxyView(APIView):
    permission_classes = [IsSuperUser]

    def _proxy(self, request: drf_request.Request, route: str) -> response.Response:
        if not (token := request.user.dooray_api_key):
            return response.Response(
                data={"detail": "먼저 Dooray 개인 토큰을 등록하세요."},
                status=status.HTTP_409_CONFLICT,
            )

        path = "/" + route.lstrip("/")
        if ".." in path or not _ALLOWED_PATH.match(path):
            return response.Response(
                data={"detail": f"허용되지 않은 Dooray 경로입니다: {path}"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            resp = nhn_cloud_dooray_client.forward(
                token=token,
                method=request.method,
                path=path,
                params=request.query_params.dict(),
                json=request.data if request.method in ("POST", "PUT", "PATCH") and request.data else None,
            )
        except DoorayError as e:
            resp = e.response  # Dooray 4xx/5xx 는 그대로 통과
        except httpx.HTTPError as e:
            return response.Response(
                data={"detail": f"Dooray 요청 실패: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            data = resp.json() if resp.content else None
        except ValueError:
            data = {"detail": resp.text}
        return response.Response(data=data, status=resp.status_code)

    get = post = put = patch = delete = _proxy
