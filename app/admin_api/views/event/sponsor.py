from __future__ import annotations

from admin_api.filtersets.event.sponsor import (
    SponsorAdminFilterSet,
    SponsorTagAdminFilterSet,
    SponsorTierAdminFilterSet,
)
from admin_api.serializers.event.sponsor import (
    SponsorAdminSerializer,
    SponsorTagAdminSerializer,
    SponsorTierAdminSerializer,
)
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from core.pagination import AdminPagination
from core.viewset.json_schema_viewset import JsonSchemaMixin
from core.viewset.selectables_viewset import SelectablesMixin
from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.sponsor.models import Sponsor, SponsorTag, SponsorTier
from rest_framework import viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorTierAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorTierAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = SponsorTierAdminFilterSet
    queryset = (
        SponsorTier.objects.filter_active()
        .prefetch_related(
            models.Prefetch(
                lookup="sponsors",
                queryset=Sponsor.objects.filter_active().select_related_with_user(),
                to_attr="_prefetched_active_sponsors",
            ),
        )
        .select_related_with_user("event")
        .order_by("-event__event_end_at", "order", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorTagAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorTagAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = SponsorTagAdminFilterSet
    queryset = (
        SponsorTag.objects.filter_active().select_related_with_user("event").order_by("-event__event_end_at", "pk")
    )


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorAdminViewSet(JsonSchemaMixin, SelectablesMixin, viewsets.ModelViewSet):
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorAdminSerializer
    permission_classes = [IsSuperUser]
    filterset_class = SponsorAdminFilterSet
    queryset = (
        Sponsor.objects.filter_active()
        .select_related_with_user("event")
        .prefetch_related("tiers", "tags")
        .order_by("-event__event_end_at", "-created_at", "pk")
    )
