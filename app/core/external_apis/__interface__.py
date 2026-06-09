from abc import ABC, abstractmethod
from typing import Any, TypedDict


class SendParameters(TypedDict):
    payload: dict[str, Any]
    send_to: str
    sent_from: str | None
    template_code: str


class NotificationSendError(Exception):
    """발송 채널이 HTTP 200을 주면서도 응답 본문 기준으로 발송을 거부한 경우."""


class NotificationServiceInterface(ABC):
    @abstractmethod
    def send_message(self, *, data: SendParameters) -> None: ...
