from logging import getLogger
from typing import TypedDict, cast

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from django.core.mail import EmailMessage

logger = getLogger(__name__)


class EmailPayload(TypedDict):
    title: str
    body: str


class EmailClient(NotificationServiceInterface):
    def send_message(self, *, data: SendParameters) -> None:
        if not data["sent_from"]:
            raise ValueError("sent_from is required to send Email.")

        payload = cast(EmailPayload, data["payload"])
        if not payload.get("title"):
            raise ValueError("title is required in payload.")

        message = EmailMessage(
            subject=payload["title"],
            body=payload.get("body", ""),
            from_email=data["sent_from"],
            to=[data["send_to"]],
        )
        message.content_subtype = "html"
        sent_count = message.send(fail_silently=False)
        logger.info("Email send results: sent_count=%s to=%s", sent_count, data["send_to"])


email_client = EmailClient()
