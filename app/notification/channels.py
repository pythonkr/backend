from django.db import models
from notification.models.base import NotificationHistoryBase, NotificationTemplateBase
from notification.models.email import EmailNotificationTemplate
from notification.models.nhn_cloud_kakao_alimtalk import NHNCloudKakaoAlimTalkNotificationTemplate
from notification.models.nhn_cloud_sms import NHNCloudSMSNotificationTemplate


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    NHN_CLOUD_SMS = "nhn_cloud_sms", "NHN Cloud SMS"
    NHN_CLOUD_KAKAO_ALIMTALK = "nhn_cloud_kakao_alimtalk", "NHN Cloud Kakao Alimtalk"

    @property
    def template_class(self) -> type[NotificationTemplateBase]:
        return {
            NotificationChannel.EMAIL: EmailNotificationTemplate,
            NotificationChannel.NHN_CLOUD_SMS: NHNCloudSMSNotificationTemplate,
            NotificationChannel.NHN_CLOUD_KAKAO_ALIMTALK: NHNCloudKakaoAlimTalkNotificationTemplate,
        }[self]

    @property
    def history_class(self) -> type[NotificationHistoryBase]:
        # Template → History reverse relation 의 related_name 이 "histories" 라는 컨벤션에 의존.
        # NotificationHistoryBase 서브클래스는 `template = ForeignKey(..., related_name="histories")` 패턴.
        return self.template_class._meta.get_field("histories").related_model
