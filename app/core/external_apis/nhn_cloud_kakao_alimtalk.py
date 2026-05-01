# https://docs.nhncloud.com/ko/Notification/KakaoTalk%20Bizmessage/ko/alimtalk-api-guide/
from logging import getLogger
from typing import Any

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from django.conf import settings
from httpx import Client

logger = getLogger(__name__)


class NHNCloudKakaoAlimTalkClient(NotificationServiceInterface):
    session: Client

    def __init__(self) -> None:
        self.session = Client(
            base_url=f"{settings.NHN_CLOUD.kakao_alimtalk.base_url}/alimtalk/v2.3/appkeys/{settings.NHN_CLOUD.app_key}",
            headers={
                "Content-Type": "application/json",
                "X-Secret-Key": settings.NHN_CLOUD.secret_key,
            },
            timeout=settings.NHN_CLOUD.kakao_alimtalk.timeout,
        )

    def send_message(self, *, data: SendParameters) -> None:
        if not data["sent_from"]:
            raise ValueError("sent_from is required to send NHN Cloud Kakao Alimtalk message.")

        body = {
            "senderKey": data["sent_from"],
            "templateCode": data["template_code"],
            "recipientList": [{"recipientNo": data["send_to"], "templateParameter": data["payload"]}],
        }
        result = self.session.post("/messages", json=body).raise_for_status().json()
        logger.info(
            "Alimtalk send results: result_code=%s, result_message=%s",
            result["header"]["resultCode"],
            result["header"]["resultMessage"],
        )

    def get_sender_list(self) -> dict[str, Any]:
        return self.session.get("/senders").raise_for_status().json()

    def list_template_categories(self) -> dict[str, Any]:
        return self.session.get("/template/categories").raise_for_status().json()

    def list_templates(self, sender_key: str, **params: Any) -> dict[str, Any]:
        return self.session.get(f"/senders/{sender_key}/templates", params=params or None).raise_for_status().json()


nhn_cloud_kakao_alimtalk_client = NHNCloudKakaoAlimTalkClient()
