import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.functions import Now

User = get_user_model()


class BaseAbstractModelQuerySet(models.QuerySet):
    def delete(self, *args, **kwargs):
        return super().update(*args, **kwargs, deleted_at=Now(), updated_at=Now())

    def hard_delete(self):
        return super().delete()

    def filter_active(self):
        return self.filter(deleted_at__isnull=True)


class BaseAbstractModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="%(class)s_created_by")
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="%(class)s_updated_by")
    deleted_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="%(class)s_deleted_by")

    objects: BaseAbstractModelQuerySet = BaseAbstractModelQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if update_fields := kwargs.get("update_fields"):
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        super().save(*args, **kwargs)
