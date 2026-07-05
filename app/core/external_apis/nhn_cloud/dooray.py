# https://helpdesk.dooray.com/share/pages/9wWo-xwiR66BO5LGshgVTg/2939987647631384419 (NHN Dooray 서비스 API)
from typing import TypedDict

from core.external_apis.__interface__ import HttpMethod
from django.conf import settings
from httpx import Client, HTTPStatusError, Response


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
    def __init__(self, response: Response) -> None:
        self.response = response
        self.status_code = response.status_code
        super().__init__(f"Dooray API error {response.status_code}")


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
        resp = self.session.request(
            method,
            path,
            params=params,
            json=json,
            headers={"Authorization": f"dooray-api {token}"},
        )
        try:
            return resp.raise_for_status()
        except HTTPStatusError as exc:
            raise DoorayError(resp) from exc

    def members_me(self, token: str) -> DoorayMember:
        return self.forward(token, "GET", "/common/v1/members/me").json().get("result", {})


nhn_cloud_dooray_client = NHNCloudDoorayClient()
