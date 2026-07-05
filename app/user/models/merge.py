from __future__ import annotations

import logging
from collections.abc import Generator, Iterable
from functools import cached_property, lru_cache
from itertools import chain

from allauth.account.models import EmailAddress
from core.const.account import MERGE_MESSAGES
from core.models import BaseAbstractModel
from core.openapi.ui_hints import admin_route_for_model
from core.util.dateutil import now_aware
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db.models.base import Model
from django.db.models.constraints import UniqueConstraint
from django.db.models.deletion import PROTECT
from django.db.models.fields import BigIntegerField, CharField, DateTimeField
from django.db.models.fields.json import JSONField
from django.db.models.fields.related import ForeignKey
from django.db.models.indexes import Index
from django.db.models.query_utils import Q
from django.db.transaction import atomic
from simple_history.manager import HistoryManager
from simple_history.models import registered_models
from simple_history.utils import bulk_update_with_history, get_history_model_for_model

from .user import UserExt

logger = logging.getLogger(__name__)


class MergeError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(MERGE_MESSAGES[code]["ko"])

    def localized(self, *, en: bool) -> str:
        return MERGE_MESSAGES[self.code]["en" if en else "ko"]


@lru_cache(maxsize=1)
def _movable_relations() -> Iterable[tuple[type[Model], Iterable[ForeignKey]]]:
    authorship = frozenset(
        f.name for f in BaseAbstractModel._meta.get_fields() if getattr(f, "related_model", None) is UserExt
    ) | {"revoked_by"}
    snapshots = {get_history_model_for_model(m) for m in registered_models.values()}
    excluded = snapshots | {UserMergeHistory, EmailAddress}
    by_model: dict[type[Model], list[ForeignKey]] = {}
    for model in apps.get_models():
        if model._meta.proxy or model in excluded:
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
            raise MergeError("target_no_verified_email")
        if EmailAddress.objects.filter(user=target, verified=False).exists():
            raise MergeError("target_unverified_email")
        if EmailAddress.objects.filter(user=source, verified=False).exists():
            raise MergeError("source_unverified_email")

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
            raise MergeError("same_account")
        if self.target.merged_to_id is not None:
            raise MergeError("target_already_merged")
        if self.source.merged_to_id is not None:
            raise MergeError("source_already_merged")

        merge_objects = chain.from_iterable(self._create_merge_objects(m, fs) for m, fs in _movable_relations())
        for merge_object in UserMergeObject.objects.bulk_create(merge_objects):
            merge_object.apply()

        for snapshot in UserMergeEmailSnapshot.objects.bulk_create(UserMergeEmailSnapshot.plan(self)):
            snapshot.apply()
        emails = EmailAddress.objects.filter(user_id=self.target_id)
        if not emails.filter(primary=True).exists():
            if primary := emails.filter(verified=True).first() or emails.first():
                primary.set_as_primary()

        self.source.is_active = False
        self.source.merged_to = self.target
        self.source.save(update_fields=["is_active", "merged_to"])

    @atomic
    def unmerge(self) -> None:
        if self.reverted_at is not None:
            raise MergeError("already_reverted")
        if self.target.merged_to_id is not None:
            raise MergeError("later_merge_first")

        for merge_object in self.merged_objects.select_related("target_type"):
            merge_object.history = self
            merge_object.undo()

        for snapshot in sorted(self.email_snapshots.all(), key=lambda s: s.before.get("verified", False)):
            snapshot.undo()

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

    @cached_property
    def target_type_model_info(self) -> dict[str, str]:
        return admin_route_for_model(self.target_type.model_class())

    @property
    def target_type_app(self) -> str:
        return self.target_type_model_info["app"]

    @property
    def target_type_resource(self) -> str:
        return self.target_type_model_info["resource"]

    def apply(self) -> None:
        self._repoint(self.history.target_id, f"account_merge:{self.history_id}")

    def undo(self) -> None:
        self._repoint(self.history.source_id, f"account_unmerge:{self.history_id}")

    def _repoint(self, user_id: object, change_reason: str) -> None:
        model = self.target_type.model_class()
        if isinstance(getattr(model, "history", None), HistoryManager):
            if not (obj := model._base_manager.filter(pk=self.target_id).first()):
                logger.warning("account merge repoint skipped: %s#%s missing", self.target_type.model, self.target_id)
                return
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


class UserMergeEmailSnapshot(BaseAbstractModel):
    history = ForeignKey(UserMergeHistory, on_delete=PROTECT, related_name="email_snapshots")
    email_id = BigIntegerField()
    before = JSONField()
    after = JSONField()

    class Meta:
        indexes = [Index(fields=["history", "email_id"])]

    def __str__(self) -> str:
        return f"EmailSnapshot #{self.email_id} {self.before}→{self.after}"

    @classmethod
    def plan(cls, history: UserMergeHistory) -> Iterable[UserMergeEmailSnapshot]:
        target_emails = {e.email: e for e in EmailAddress.objects.filter(user_id=history.target_id)}
        target_has_primary = any(e.primary for e in target_emails.values())
        for src in EmailAddress.objects.filter(user_id=history.source_id):
            if not (dup := target_emails.get(src.email)):
                before: dict = {"user_id": history.source_id}
                after: dict = {"user_id": history.target_id}
                if target_has_primary and src.primary:
                    before["primary"], after["primary"] = True, False
                yield cls(history=history, email_id=src.pk, before=before, after=after)
                target_has_primary = target_has_primary or src.primary
            elif src.verified and not dup.verified:
                # 소스 강등을 타깃 승격보다 먼저 — unique_verified_email 순간 위반 방지
                yield cls(history=history, email_id=src.pk, before={"verified": True}, after={"verified": False})
                yield cls(history=history, email_id=dup.pk, before={"verified": False}, after={"verified": True})

    def apply(self) -> None:
        EmailAddress.objects.filter(pk=self.email_id).update(**self.after)

    def undo(self) -> None:
        EmailAddress.objects.filter(pk=self.email_id).update(**self.before)
