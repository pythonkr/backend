import typing

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from event.presentation.models import Presentation, PresentationSpeaker
from user.models import UserExt


class ModificationAuditQuerySet(BaseAbstractModelQuerySet):
    def filter_requested(self, instance: models.Model) -> typing.Self:
        return self.filter_active().filter(
            instance_type__app_label=instance._meta.app_label,
            instance_type__model=instance._meta.model_name,
            instance_id=str(instance.pk),
            status=ModificationAudit.Status.REQUESTED,
        )


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

    def apply_modification(self, save: bool = False) -> models.Model:
        for field, value in self.modification_data.items():
            if isinstance(value, list):
                # One to Many case
                sub_value_map = {sub_value["id"]: sub_value for sub_value in value}
                if not (sub_instances := list(getattr(self.instance, field).filter(pk__in=sub_value_map))):
                    continue

                for sub_instance in sub_instances:
                    sub_data = sub_value_map[str(sub_instance.pk)]
                    for sub_field, sub_value in sub_data.items():
                        setattr(sub_instance, sub_field, sub_value)

                    if save:
                        sub_instance.save()
            elif isinstance(value, dict):
                # One to One case
                if not (sub_instance := getattr(self.instance, field, None)):
                    continue

                for sub_field, sub_value in value.items():
                    setattr(sub_instance, sub_field, sub_value)

                if save:
                    sub_instance.save()
                else:
                    setattr(self.instance, field, sub_instance)
            else:
                # 일반 필드 업데이트
                setattr(self.instance, field, value)

        if save:
            self.instance.save()

        return self.instance


class ModificationAuditComment(BaseAbstractModel):
    audit = models.ForeignKey(ModificationAudit, on_delete=models.PROTECT, related_name="comments")
    content = models.TextField(blank=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["audit"]), models.Index(fields=["created_at"])]

    def __str__(self) -> str:
        return f"[댓글] {self.audit}"
