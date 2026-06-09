from typing import ClassVar

from core.external_apis.nhn_cloud.sms import NHNCloudSMSClient, nhn_cloud_sms_client
from django.db import models
from notification.models.base import (
    NotificationHistoryBase,
    NotificationHistoryQuerySet,
    NotificationHistorySentToBase,
    NotificationTemplateBase,
)


class NHNCloudSMSNotificationTemplate(NotificationTemplateBase):
    html_template_name: ClassVar[str] = "nhn_cloud_sms_preview.html"


class NHNCloudSMSNotificationHistorySentTo(NotificationHistorySentToBase):
    history = models.ForeignKey("NHNCloudSMSNotificationHistory", on_delete=models.PROTECT, related_name="sent_to_list")


class NHNCloudSMSNotificationHistoryQuerySet(
    NotificationHistoryQuerySet["NHNCloudSMSNotificationHistory", NHNCloudSMSNotificationTemplate],
):
    pass


class NHNCloudSMSNotificationHistory(NotificationHistoryBase):
    client: ClassVar[NHNCloudSMSClient] = nhn_cloud_sms_client
    template_class: ClassVar[type[NHNCloudSMSNotificationTemplate]] = NHNCloudSMSNotificationTemplate
    sent_to_class: ClassVar[type[NHNCloudSMSNotificationHistorySentTo]] = NHNCloudSMSNotificationHistorySentTo

    template = models.ForeignKey(
        NHNCloudSMSNotificationTemplate,
        on_delete=models.PROTECT,
        related_name="histories",
        null=True,
        blank=True,
    )

    objects: NHNCloudSMSNotificationHistoryQuerySet = (
        NHNCloudSMSNotificationHistoryQuerySet.as_manager()  # type: ignore[misc, assignment]
    )
