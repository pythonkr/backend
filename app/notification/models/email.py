from typing import ClassVar

from core.external_apis.__interface__ import SendParameters
from core.external_apis.smtp_email import EmailClient, email_client
from django.db import models
from notification.models.base import NotificationHistoryBase, NotificationTemplateBase


class EmailNotificationTemplate(NotificationTemplateBase):
    html_template_name: ClassVar[str] = "email_preview.html"

    from_address = models.EmailField(null=False, blank=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_email_noti_template_code",
            ),
            models.UniqueConstraint(
                fields=["code", "title"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_email_noti_template_code_title",
            ),
        ]


class EmailNotificationHistory(NotificationHistoryBase):
    client: ClassVar[EmailClient] = email_client

    template = models.ForeignKey(
        EmailNotificationTemplate,
        on_delete=models.PROTECT,
        related_name="histories",
    )

    @property
    def template_code(self) -> str:
        return self.template.code

    def build_send_parameters(self) -> SendParameters:
        return SendParameters(
            payload=self.template.render(context=self.context),
            send_to=self.send_to,
            template_code=self.template_code,
            sent_from=self.template.from_address,
        )
