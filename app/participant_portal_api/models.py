from __future__ import annotations

import types
import typing

from core.const.datetime import KST
from core.external_apis.slack.blocks import (
    SlackBlocks,
    SlackHeaderParentBlock,
    SlackMarkDownChildBlock,
    SlackPlainTextChildBlock,
    SlackSectionParentBlock,
    SlackURLButtonAccessoryBlock,
)
from core.external_apis.slack.client import SlackClient
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.util.django_orm import (
    apply_diff_to_jsonized_models,
    apply_diff_to_model,
    json_to_simplenamespace,
    model_to_identifier,
)
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from event.presentation.models import Presentation, PresentationSpeaker
from user.models import UserExt

T = typing.TypeVar("T", bound=models.Model)
AUDIT_TYPE: dict[models.Model, str] = {
    Presentation: "발표",
    UserExt: "프로필",
}


class ModificationAuditQuerySet(BaseAbstractModelQuerySet):
    def filter_by_instance(self, instance: models.Model) -> typing.Self:
        return self.filter_active().filter(
            instance_type__app_label=instance._meta.app_label,
            instance_type__model=instance._meta.model_name,
            instance_id=str(instance.pk),
        )

    def filter_requested(self, instance: models.Model) -> typing.Self:
        return self.filter_active().filter_by_instance(instance).filter(status=ModificationAudit.Status.REQUESTED)


class ModificationAudit(BaseAbstractModel):
    class Action(models.TextChoices):
        CREATE = "create", "생성"
        UPDATE = "update", "수정"
        DELETE = "delete", "삭제"

    class Status(models.TextChoices):
        REQUESTED = "requested", "수정 심사 요청됨"
        APPROVED = "approved", "수정 요청이 승인되어 적용됨"
        REJECTED = "rejected", "운영자에 의해 수정 요청 반려됨"
        CANCELLED = "cancelled", "수정 요청자가 철회함"

    REGISTERED_INSTANCE_TYPES = (Presentation, PresentationSpeaker, UserExt)

    action = models.CharField(max_length=16, choices=Action.choices, default=Action.UPDATE)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.REQUESTED)
    original_data = models.JSONField(default=dict, blank=False)
    modification_data = models.JSONField(default=dict, blank=False)

    instance_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    # BaseAbstractModel의 pk는 UUID이나, UserExt의 경우 pk가 IntegerField이므로 중간 절충점인 CharField를 사용합니다.
    # https://docs.djangoproject.com/en/5.2/ref/contrib/contenttypes/#django.contrib.contenttypes.fields.GenericForeignKey
    # 의 Primary key type compatibility 문단 참조
    # 추가로 PostgreSQL의 NAMEDATALEN(=63)과 호환되도록 max_length=63으로 설정합니다.
    instance_id = models.CharField(max_length=63, blank=False)
    instance = GenericForeignKey("instance_type", "instance_id")

    objects: ModificationAuditQuerySet = ModificationAuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["instance_type", "instance_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["created_by"]),
        ]

    def __str__(self) -> str:
        return str(self.instance)

    @property
    def instance_identifier(self) -> str:
        return model_to_identifier(self.instance)

    @property
    def fake_original_instance(self) -> types.SimpleNamespace:
        return json_to_simplenamespace(self.original_data, self.instance_identifier)

    @property
    def fake_modified_instance(self) -> types.SimpleNamespace:
        updated_data = apply_diff_to_jsonized_models(self.original_data, self.modification_data)
        return json_to_simplenamespace(updated_data, self.instance_identifier)

    def apply_modification(self) -> models.Model:
        apply_diff_to_model(self.modification_data)
        self.instance.refresh_from_db()
        return self.instance

    def notify_creation_to_slack(self) -> None:
        if not (audit_noti_channel := settings.SLACK.modification_audit_notification_channel):
            return

        created_at_kst_str = self.created_at.astimezone(KST).strftime("%y년 %m월 %d일 %H시 %M분")
        audit_instance_type_str = AUDIT_TYPE.get(self.instance_type.model_class(), "알 수 없음")
        blocks = SlackBlocks(
            blocks=[
                SlackHeaderParentBlock(text=SlackPlainTextChildBlock(text=":pencil: 수정 요청이 들어왔어요!")),
                SlackSectionParentBlock(
                    fields=[
                        SlackMarkDownChildBlock(text=f"*수정 유형*\n{audit_instance_type_str}"),
                        SlackMarkDownChildBlock(text=f"*요청 시간*\n{created_at_kst_str}"),
                        SlackMarkDownChildBlock(text=f"*요청자*\n{self.created_by.nickname}"),
                        SlackMarkDownChildBlock(text=f"*요청 ID*\n{self.id}"),
                    ]
                ),
                SlackSectionParentBlock(
                    text=SlackMarkDownChildBlock(text="어드민에서 수정 내역을 확인 후 승인 또는 반려해주세요."),
                    accessory=SlackURLButtonAccessoryBlock(
                        text=SlackPlainTextChildBlock(text="수정 심사 페이지 열기"),
                        url=f"{settings.FRONTEND_DOMAIN.admin}/modification-audit/{self.id}",
                    ),
                ),
            ]
        )

        SlackClient().send_message(
            channel_id=audit_noti_channel, text="새로운 수정 요청이 도착했습니다.", blocks=blocks
        )


class ModificationAuditComment(BaseAbstractModel):
    audit = models.ForeignKey(ModificationAudit, on_delete=models.PROTECT, related_name="comments")
    content = models.TextField(blank=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["audit"]), models.Index(fields=["created_at"])]

    def __str__(self) -> str:
        return f"[댓글] {self.audit}"
