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


class EmailNotificationHistorySentTo(NotificationHistorySentToBase):
    history = models.ForeignKey("EmailNotificationHistory", on_delete=models.PROTECT, related_name="sent_to_list")

    @property
    def payload(self) -> dict[str, Any]:
        rendered = self.render()
        rendered["body"] = self.render_as_html()
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
