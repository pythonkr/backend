# https://docs.nhncloud.com/ko/Notification/SMS/ko/api-guide/
from logging import getLogger
from typing import Any, TypedDict, cast

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from django.conf import settings
from httpx import Client

logger = getLogger(__name__)


class SMSPayload(TypedDict, total=False):
    title: str
    body: str


class NHNCloudSMSClient(NotificationServiceInterface):
    session: Client

    def __init__(self) -> None:
        self.session = Client(
            base_url=f"{settings.NHN_CLOUD.sms.base_url}/sms/v3.0/appKeys/{settings.NHN_CLOUD.app_key}",
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "X-Secret-Key": settings.NHN_CLOUD.secret_key,
            },
            timeout=settings.NHN_CLOUD.sms.timeout,
        )

    def send_message(self, *, data: SendParameters) -> None:
        if not data["sent_from"]:
            raise ValueError("sent_from is required to send NHN Cloud SMS message.")

        payload = cast(SMSPayload, data["payload"])
        if not payload.get("body"):
            raise ValueError("body is required in payload.")

        body: dict[str, Any] = {
            "sendNo": data["sent_from"],
            "body": payload["body"],
            "recipientList": [{"recipientNo": data["send_to"]}],
        }
        if data["template_code"]:
            body["templateId"] = data["template_code"]

        if title := payload.get("title"):
            body["title"] = title
            url = "/sender/mms"
        else:
            url = "/sender/sms"

        result = self.session.post(url, json=body).raise_for_status().json()
        logger.info(
            "SMS send results: result_code=%s, result_message=%s",
            result["header"]["resultCode"],
            result["header"]["resultMessage"],
        )


nhn_cloud_sms_client = NHNCloudSMSClient()
