from __future__ import annotations

from admin_api.serializers.event.sponsor import (
    SponsorAdminSerializer,
    SponsorTagAdminSerializer,
    SponsorTierAdminSerializer,
)
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
from rest_framework import viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorTierAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorTierAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = (
        SponsorTier.objects.filter_active()
        .prefetch_related(
            models.Prefetch(
                lookup="sponsors",
                queryset=Sponsor.objects.filter_active().select_related("created_by", "updated_by", "deleted_by"),
                to_attr="_prefetched_active_sponsors",
            ),
        )
        .select_related("created_by", "updated_by", "deleted_by")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorTagAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorTagAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = SponsorTag.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Sponsor.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")
