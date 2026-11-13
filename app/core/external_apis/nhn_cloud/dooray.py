# https://helpdesk.dooray.com/share/pages/9wWo-xwiR66BO5LGshgVTg/2939987647631384419 (NHN Dooray 서비스 API)
from typing import TypedDict

from core.external_apis.__interface__ import HttpMethod
from django.conf import settings
from httpx import Client, HTTPError, HTTPStatusError, Response


class DoorayMemberOrganization(TypedDict):
    id: str


class DoorayMember(TypedDict, total=False):
    id: str
    idProviderType: str  # sso | service
    idProviderUserId: str
    name: str
    userCode: str
    externalEmailAddress: str
    defaultOrganization: DoorayMemberOrganization
    locale: str
    timezoneName: str
    englishName: str
    nativeName: str
    nickname: str
    displayMemberId: str


class DoorayError(Exception):
    # response=None: 응답을 받지 못한 실패(연결 끊김·타임아웃 등)
    def __init__(self, response: Response | None = None) -> None:
        self.response = response
        self.status_code = response.status_code if response is not None else None
        super().__init__(f"Dooray API error {self.status_code}" if response is not None else "Dooray API unreachable")


class NHNCloudDoorayClient:
    session: Client

    def __init__(self) -> None:
        self.session = Client(base_url=settings.DOORAY.base_url, timeout=settings.DOORAY.timeout)

    def forward(
        self,
        token: str,
        method: HttpMethod,
        path: str,
        *,
        params: dict | None = None,
        json: object | None = None,
    ) -> Response:
        try:
            return self.session.request(
                method,
                path,
                params=params,
                json=json,
                headers={"Authorization": f"dooray-api {token}"},
            ).raise_for_status()
        except HTTPStatusError as exc:
            raise DoorayError(exc.response) from exc
        except HTTPError as exc:
            raise DoorayError() from exc

    def members_me(self, token: str) -> DoorayMember:
        return self.forward(token, "GET", "/common/v1/members/me").json().get("result", {})


nhn_cloud_dooray_client = NHNCloudDoorayClient()
