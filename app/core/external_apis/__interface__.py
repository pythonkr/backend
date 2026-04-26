from abc import ABC, abstractmethod
from typing import Any, TypedDict


class SendParameters(TypedDict):
    payload: dict[str, Any]
    send_to: str
    sent_from: str | None
    template_code: str


class NotificationServiceInterface(ABC):
    @abstractmethod
    def send_message(self, *, data: SendParameters) -> None: ...
