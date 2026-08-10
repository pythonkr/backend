from email.policy import default as default_email_policy
from logging import getLogger
from typing import TypedDict, cast

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from django.core.mail import EmailMessage

logger = getLogger(__name__)

# 기본값 78이면 긴 한글 제목이 RFC 2047 상한(75자)을 넘는 encoded-word로 접혀 일부 클라이언트에서 깨진다.
_EMAIL_POLICY = default_email_policy.clone(max_line_length=76)


class _SafeHeaderEmailMessage(EmailMessage):
    # backend가 message()를 인자 없이 호출하므로 기본 policy 자체를 갈아끼운다.
    def message(self, *, policy=_EMAIL_POLICY):  # type: ignore[no-untyped-def]
        return super().message(policy=policy)


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

        message = _SafeHeaderEmailMessage(
            subject=payload["title"],
            body=payload.get("body", ""),
            from_email=data["sent_from"],
            to=[data["send_to"]],
        )
        message.content_subtype = "html"
        sent_count = message.send(fail_silently=False)
        logger.info("Email send results: sent_count=%s to=%s", sent_count, data["send_to"])


email_client = EmailClient()
