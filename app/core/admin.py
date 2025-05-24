from core.models import BaseAbstractModel
from django.contrib import admin
from django.db import models
from django.forms import ModelForm
from django.http import HttpRequest

INITIAL_FIELDS = INITIAL_READONLY_FIELDS = [
    "id",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
]


class AdminProtocol(admin.ModelAdmin):
    model: type[BaseAbstractModel]


class BaseAbstractModelAdminMixin(AdminProtocol):
    def get_queryset(self, request: HttpRequest) -> models.QuerySet[BaseAbstractModel]:
        """Override the default queryset to filter out soft-deleted objects."""
        return super().get_queryset(request).filter_active().select_related("created_by", "updated_by", "deleted_by")

    def save_model(self, request: HttpRequest, obj: BaseAbstractModel, form: ModelForm, change: bool) -> None:
        """Override save_model to set created_by and updated_by fields."""
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def get_fields(self, request: HttpRequest, obj: models.Model | None = None) -> list[str]:
        fields = list(super().get_fields(request, obj))
        for field in INITIAL_FIELDS:
            if field not in fields:
                fields.append(field)
        return fields

    def get_readonly_fields(self, request, obj: models.Model | None = None) -> list[str]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        for field in INITIAL_READONLY_FIELDS:
            if field not in readonly_fields:
                readonly_fields.append(field)
        return readonly_fields
