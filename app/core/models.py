import collections.abc
import typing
import uuid

from core.util.thread_local import get_current_user
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

if typing.TYPE_CHECKING:
    from user.models import UserExt  # noqa: F401

User = get_user_model()

AUDIT_CHOICE_META_SCHEMA: dict[str, dict[str, str]] = {
    "created_by": {"label": "생성자", "type": "string", "filter": "select"},
    "updated_by": {"label": "수정자", "type": "string", "filter": "select"},
    "created_at": {"label": "생성일시", "type": "string", "filter": "search"},
    "updated_at": {"label": "수정일시", "type": "string", "filter": "search"},
}


class BaseAbstractModelQuerySet(models.QuerySet):
    def create(self, **kwargs: dict) -> models.Model:
        current_user = get_current_user()
        return super().create(**(kwargs | {"created_by": current_user, "updated_by": current_user}))

    def update(self, **kwargs: dict) -> int:
        if "updated_by" not in kwargs and "updated_by_id" not in kwargs:
            kwargs |= {"updated_by": get_current_user()}
        return super().update(**kwargs)

    def delete(self) -> int:  # type: ignore[override]
        return super().update(deleted_by=get_current_user(), deleted_at=Now())

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        return super().delete()

    def filter_active(self) -> typing.Self:
        return self.filter(deleted_at__isnull=True)

    def select_related_with_user(self, *fields) -> typing.Self:
        _fields = set(fields) | {"created_by", "updated_by", "deleted_by"}
        return self.select_related(*_fields)

    def get_choices_queryset(self) -> typing.Self:
        fields = set(self.model.choices_select_related)
        if self.model.choices_meta_schema:
            fields |= {"created_by", "updated_by"}  # audit 메타 출력을 위한 join
        return self.select_related(*fields) if fields else self.all()


class BaseAbstractModel(models.Model):
    choices_select_related: typing.ClassVar[tuple[str, ...]] = ()
    choices_meta_schema: typing.ClassVar[dict[str, dict[str, str]]] = {}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey["UserExt", "UserExt"](
        User, on_delete=models.PROTECT, null=True, related_name="%(class)s_created_by"
    )
    updated_by = models.ForeignKey["UserExt", "UserExt"](
        User, on_delete=models.PROTECT, null=True, related_name="%(class)s_updated_by"
    )
    deleted_by = models.ForeignKey["UserExt", "UserExt"](
        User, on_delete=models.PROTECT, null=True, related_name="%(class)s_deleted_by"
    )

    objects: BaseAbstractModelQuerySet = BaseAbstractModelQuerySet.as_manager()  # type: ignore[misc, assignment]

    class Meta:
        abstract = True

    def get_choice_meta(self) -> dict:
        if not self.choices_meta_schema:
            return {}
        return self._choice_meta_fields() | self.get_audit_choice_meta()

    def _choice_meta_fields(self) -> dict:
        return {}

    def get_audit_choice_meta(self) -> dict:
        return {
            "created_by": self.created_by_id and str(self.created_by),
            "updated_by": self.updated_by_id and str(self.updated_by),
            "created_at": self.created_at and timezone.localtime(self.created_at).isoformat(),
            "updated_at": self.updated_at and timezone.localtime(self.updated_at).isoformat(),
        }

    def save(  # type: ignore[override]
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: collections.abc.Iterable[str] | None = None,
    ) -> None:
        if update_fields:
            update_fields = set(update_fields) | {"updated_at", "updated_by"}
        self.updated_by = get_current_user()
        super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)

    def delete(self, using: str | None = None) -> None:
        self.deleted_at = Now()
        self.deleted_by = get_current_user()
        super().save(using=using, update_fields={"deleted_by", "deleted_at"})


class MarkdownField(models.TextField):
    is_markdown = True
