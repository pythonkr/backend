from email.policy import SMTP as SMTP_EMAIL_POLICY
from logging import getLogger
from smtplib import SMTPServerDisconnected
from threading import Lock
from typing import TypedDict, cast

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from django.core.mail import EmailMessage, get_connection
from django.core.mail.backends.base import BaseEmailBackend

logger = getLogger(__name__)

# 기본값 78이면 긴 한글 제목이 RFC 2047 상한(75자)을 넘는 encoded-word로 접혀 일부 클라이언트에서 깨진다.
_EMAIL_POLICY = SMTP_EMAIL_POLICY.clone(max_line_length=76)


class _SafeHeaderEmailMessage(EmailMessage):
    # SMTP 백엔드가 policy를 명시로 넘기므로, 기본 인자가 아니라 인자 자체를 무시해야 적용된다.
    def message(self, *, policy=None):  # type: ignore[no-untyped-def]
        return super().message(policy=_EMAIL_POLICY)


class EmailPayload(TypedDict):
    title: str
    body: str


class EmailClient(NotificationServiceInterface):
    def __init__(self) -> None:
        # Gmail은 메일마다 로그인하면 "454 Too many login attempts"로 차단하므로 커넥션을 프로세스 단위로 재사용한다.
        self._connection: BaseEmailBackend | None = None
        self._lock = Lock()

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

        with self._lock:
            sent_count = self._send(message)
        logger.info("Email send results: sent_count=%s to=%s", sent_count, data["send_to"])

    def _send(self, message: EmailMessage) -> int:
        # send_messages()는 이미 열린 커넥션이면 발송 후 닫지 않는다 — open()을 먼저 해야 재사용이 성립한다.
        for is_last_attempt in (False, True):
            if self._connection is None:
                self._connection = get_connection()
                self._connection.open()
            try:
                return self._connection.send_messages([message])
            except SMTPServerDisconnected:
                # 유휴 커넥션을 서버가 끊은 경우. 메시지가 수락되기 전이므로 재연결 후 한 번만 재시도한다.
                self._connection = None
                if is_last_attempt:
                    raise
        return 0


email_client = EmailClient()
