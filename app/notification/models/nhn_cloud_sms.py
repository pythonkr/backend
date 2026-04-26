from typing import ClassVar

from core.external_apis.__interface__ import SendParameters
from core.external_apis.nhn_cloud_sms import NHNCloudSMSClient, nhn_cloud_sms_client
from django.db import models
from notification.models.base import NotificationHistoryBase, NotificationTemplateBase


class NHNCloudSMSNotificationTemplate(NotificationTemplateBase):
    html_template_name: ClassVar[str] = "nhn_cloud_sms_preview.html"

    from_no = models.CharField(max_length=13, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_nhn_cloud_sms_noti_template_code",
            ),
            models.UniqueConstraint(
                fields=["code", "title"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_nhn_cloud_sms_noti_template_code_title",
            ),
        ]


class NHNCloudSMSNotificationHistory(NotificationHistoryBase):
    client: ClassVar[NHNCloudSMSClient] = nhn_cloud_sms_client

    template = models.ForeignKey(
        NHNCloudSMSNotificationTemplate,
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
            sent_from=self.template.from_no,
        )
