from __future__ import annotations

from collections.abc import Generator, Iterable
from functools import lru_cache
from itertools import chain

from allauth.account.models import EmailAddress
from core.models import BaseAbstractModel
from core.util.dateutil import now_aware
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db.models.base import Model
from django.db.models.constraints import UniqueConstraint
from django.db.models.deletion import PROTECT
from django.db.models.fields import CharField, DateTimeField
from django.db.models.fields.related import ForeignKey
from django.db.models.indexes import Index
from django.db.models.query_utils import Q
from django.db.transaction import atomic
from simple_history.manager import HistoryManager
from simple_history.models import registered_models
from simple_history.utils import bulk_update_with_history, get_history_model_for_model

from .user import UserExt


@lru_cache(maxsize=1)
def _movable_relations() -> Iterable[tuple[type[Model], Iterable[ForeignKey]]]:
    authorship = frozenset(
        f.name for f in BaseAbstractModel._meta.get_fields() if getattr(f, "related_model", None) is UserExt
    ) | {"revoked_by"}
    snapshots = {get_history_model_for_model(m) for m in registered_models.values()}
    by_model: dict[type[Model], list[ForeignKey]] = {}
    for model in apps.get_models():
        if model._meta.proxy or model is UserMergeHistory or model in snapshots:
            continue
        if model._meta.app_label == "admin":  # LogEntry
            continue
        for field in model._meta.get_fields():
            if not (field.is_relation and not field.auto_created and field.related_model is UserExt):
                continue
            if field.many_to_many or field.name in authorship:
                continue
            by_model.setdefault(model, []).append(field)
    return tuple((model, tuple(fields)) for model, fields in by_model.items())


class UserMergeHistory(BaseAbstractModel):
    source = ForeignKey("user.UserExt", on_delete=PROTECT, related_name="+")
    target = ForeignKey("user.UserExt", on_delete=PROTECT, related_name="+")
    reverted_at = DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"UserMerge {self.source_id}→{self.target_id}"

    @property
    def is_self_merge(self) -> bool:
        return self.created_by_id is not None and self.created_by_id == self.target_id

    @staticmethod
    def assert_self_mergeable(source: UserExt, target: UserExt) -> None:
        if not EmailAddress.objects.filter(user=target).exists():
            msg = "남길 계정에 인증된 이메일이 필요합니다. 이메일을 추가하고 인증한 뒤 다시 시도해 주세요."
            raise ValueError(msg)
        if EmailAddress.objects.filter(user=target, verified=False).exists():
            msg = "남길 계정에 인증되지 않은 이메일이 있습니다. 인증을 완료하거나 해당 이메일을 삭제한 뒤 다시 시도해 주세요."
            raise ValueError(msg)
        if EmailAddress.objects.filter(user=source, verified=False).exists():
            msg = "합칠 계정에 인증되지 않은 이메일이 있습니다. 해당 계정으로 로그인해 인증을 완료하거나 삭제한 뒤 다시 시도해 주세요."
            raise ValueError(msg)

    def _create_merge_objects(
        self, model: type[Model], fields: Iterable[ForeignKey]
    ) -> Generator[UserMergeObject, None, None]:
        aggregated: dict[object, tuple[Model, list[str]]] = {}

        for field in fields:
            groups: list[tuple[tuple[str, ...], Q | None]] = []
            if field.unique:
                groups.append(((), None))
            for ut in model._meta.unique_together:
                if field.name in ut:
                    groups.append((tuple(model._meta.get_field(f).attname for f in ut if f != field.name), None))
            for constraint in model._meta.constraints:
                if isinstance(constraint, UniqueConstraint) and field.name in constraint.fields:
                    others = tuple(model._meta.get_field(f).attname for f in constraint.fields if f != field.name)
                    groups.append((others, constraint.condition))

            for row in model._base_manager.filter(**{field.attname: self.source_id}):
                movable = True
                for other_attnames, condition in groups:
                    if condition is not None and not model._base_manager.filter(pk=row.pk).filter(condition).exists():
                        continue
                    qs = model._base_manager.filter(
                        **{field.attname: self.target_id},
                        **{a: getattr(row, a) for a in other_attnames},
                    )
                    if (qs.filter(condition) if condition is not None else qs).exists():
                        movable = False
                        break
                if movable:
                    aggregated.setdefault(row.pk, (row, []))[1].append(field.name)

        for row, names in aggregated.values():
            yield UserMergeObject(history=self, target_object=row, field_names=names)

    @atomic
    def merge(self) -> None:
        if self.source.pk == self.target.pk:
            raise ValueError("같은 계정끼리는 병합할 수 없습니다.")
        if self.target.merged_to_id is not None:
            raise ValueError("남길 계정이 이미 다른 계정에 병합되어 있습니다.")
        if self.source.merged_to_id is not None:
            raise ValueError("합칠 계정이 이미 다른 계정에 병합되어 있습니다.")

        merge_objects = chain.from_iterable(self._create_merge_objects(m, fs) for m, fs in _movable_relations())
        for merge_object in UserMergeObject.objects.bulk_create(merge_objects):
            merge_object.apply()

        self.source.is_active = False
        self.source.merged_to = self.target
        self.source.save(update_fields=["is_active", "merged_to"])

    @atomic
    def unmerge(self) -> None:
        if self.reverted_at is not None:
            raise ValueError("이미 되돌린 병합입니다.")

        for merge_object in self.merged_objects.select_related("target_type"):
            merge_object.history = self
            merge_object.undo()

        self.source.is_active = True
        self.source.merged_to = None
        self.source.save(update_fields=["is_active", "merged_to"])

        self.reverted_at = now_aware()
        self.save(update_fields=["reverted_at"])


class UserMergeObject(BaseAbstractModel):
    history = ForeignKey(UserMergeHistory, on_delete=PROTECT, related_name="merged_objects")
    target_type = ForeignKey(ContentType, on_delete=PROTECT)
    target_id = CharField(max_length=255)
    target_object = GenericForeignKey("target_type", "target_id")
    field_names = ArrayField(CharField(max_length=63))

    class Meta:
        indexes = [Index(fields=["target_type", "target_id"])]

    def __str__(self) -> str:
        return f"{self.target_type.model}#{self.target_id} {self.field_names}"

    def apply(self) -> None:
        self._repoint(self.history.target_id, f"account_merge:{self.history_id}")

    def undo(self) -> None:
        self._repoint(self.history.source_id, f"account_unmerge:{self.history_id}")

    def _repoint(self, user_id: object, change_reason: str) -> None:
        model = self.target_type.model_class()
        if isinstance(getattr(model, "history", None), HistoryManager):
            obj = model._base_manager.get(pk=self.target_id)
            for name in self.field_names:
                setattr(obj, model._meta.get_field(name).attname, user_id)
            bulk_update_with_history(
                [obj],
                model,
                self.field_names,
                default_user=self.history.created_by,
                default_change_reason=change_reason,
            )
        else:
            attnames = {model._meta.get_field(name).attname: user_id for name in self.field_names}
            model._base_manager.filter(pk=self.target_id).update(**attnames)
