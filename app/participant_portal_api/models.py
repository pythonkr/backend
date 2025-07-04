import contextlib
import typing

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from event.presentation.models import Presentation, PresentationSpeaker
from rest_framework import serializers
from user.models import UserExt

T = typing.TypeVar("T", bound=models.Model)


def _apply_dict_to_model(instance: T, data: dict, save: bool = False) -> T:
    model_class = type(instance)

    for field_name, value in data.items():
        with contextlib.suppress(FieldDoesNotExist):
            field = model_class._meta.get_field(field_name)

            if isinstance(field, models.ForeignKey):
                # One to One or One to Many case
                if isinstance(value, dict):
                    if not (sub_instance := field.related_model.objects.filter(pk=value.get("id")).first()):
                        continue
                    setattr(instance, field_name, _apply_dict_to_model(sub_instance, value), save)
                elif isinstance(value, (int, str)):
                    if not (sub_instance := field.related_model.objects.filter(pk=value).first()):
                        continue
                    setattr(instance, field_name, sub_instance.pk if field_name.endswith("_id") else sub_instance)
            elif isinstance(field, models.ManyToOneRel):
                if save:
                    if not all(isinstance(v, dict) and "id" in v for v in value):
                        continue
                    for sub_value in value:
                        getattr(instance, field).filter(pk=sub_value.pop("id")).update(**sub_value)
            else:
                # 일반 필드 업데이트
                setattr(instance, field_name, value)

    if save:
        instance.save()

    return instance


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

    def get_applied_data(self, serializer_class: type[serializers.ModelSerializer]) -> dict:
        one_to_many: dict[str, dict[str, dict[str, typing.Any]]] = {
            k: {sv["id"]: sv for sv in v}
            for k, v in self.modification_data.items()
            if isinstance(v, list) and all(isinstance(i, dict) and "id" in i for i in v)
        }

        modified_instance = _apply_dict_to_model(instance=self.instance, data=self.modification_data, save=False)
        modified_data = serializer_class(instance=modified_instance).data

        for field_name, mod_values in one_to_many.items():
            if field_name not in modified_data:
                continue

            for field_value in modified_data[field_name]:
                if not (isinstance(field_value, dict) and (value_id := field_value.get("id"))):
                    continue

                if value_id in mod_values:
                    # 기존 값에 수정된 값을 병합합니다.
                    field_value.update(mod_values[value_id])

        return modified_data

    def apply_modification(self) -> models.Model:
        return _apply_dict_to_model(instance=self.instance, data=self.modification_data, save=True)


class ModificationAuditComment(BaseAbstractModel):
    audit = models.ForeignKey(ModificationAudit, on_delete=models.PROTECT, related_name="comments")
    content = models.TextField(blank=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["audit"]), models.Index(fields=["created_at"])]

    def __str__(self) -> str:
        return f"[댓글] {self.audit}"
