from typing import Any, ClassVar

from core.external_apis.smtp_email import EmailClient, email_client
from django.db import models
from notification.models.base import (
    NotificationHistoryBase,
    NotificationHistoryQuerySet,
    NotificationHistorySentToBase,
    NotificationTemplateBase,
)


class EmailNotificationTemplate(NotificationTemplateBase):
    html_template_name: ClassVar[str] = "email_preview.html"
    required_data_keys: ClassVar[tuple[str, ...]] = ("title", "body")


class EmailNotificationHistorySentTo(NotificationHistorySentToBase):
    history = models.ForeignKey("EmailNotificationHistory", on_delete=models.PROTECT, related_name="sent_to_list")

    @property
    def payload(self) -> dict[str, Any]:
        # body는 HTML이라 context를 escape, title은 메일 제목(plain text)이라 그대로 둔다.
        rendered = self.render()
        rendered["body"] = self.render(autoescape=True).get("body", "")
        return rendered


class EmailNotificationHistoryQuerySet(
    NotificationHistoryQuerySet["EmailNotificationHistory", EmailNotificationTemplate],
):
    pass


class EmailNotificationHistory(NotificationHistoryBase):
    client: ClassVar[EmailClient] = email_client
    template_class: ClassVar[type[EmailNotificationTemplate]] = EmailNotificationTemplate
    sent_to_class: ClassVar[type[EmailNotificationHistorySentTo]] = EmailNotificationHistorySentTo

    template = models.ForeignKey(
        EmailNotificationTemplate,
        on_delete=models.PROTECT,
        related_name="histories",
        null=True,
        blank=True,
    )

    objects: EmailNotificationHistoryQuerySet = (
        EmailNotificationHistoryQuerySet.as_manager()  # type: ignore[misc, assignment]
    )
