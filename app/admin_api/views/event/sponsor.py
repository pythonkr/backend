from __future__ import annotations

from admin_api.serializers.event.sponsor import SponsorAdminSerializer, SponsorTierAdminSerializer
from core.const.regex import UUID_V4_PATTERN
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.sponsor.models import Sponsor, SponsorTier, SponsorTierSponsorRelation
from rest_framework import decorators, exceptions, response, status, viewsets

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

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_SPONSOR],
        responses={status.HTTP_200_OK: SponsorAdminSerializer(many=True)},
    )
    @decorators.action(detail=True, methods=["get"], url_path="sponsors")
    def list_sponsors(self, *args: tuple, **kwargs: dict) -> response.Response:
        tier: SponsorTier = self.get_object()
        return response.Response(data=SponsorAdminSerializer(instance=tier.active_sponsors, many=True).data)

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR], responses={status.HTTP_201_CREATED: SponsorAdminSerializer})
    @decorators.action(detail=True, methods=["post"], url_path=f"sponsors/(?P<sponsor_id>{UUID_V4_PATTERN})")
    def add_sponsor(self, sponsor_id: str, *args: tuple, **kwargs: dict) -> response.Response:
        tier: SponsorTier = self.get_object()
        if not (sponsor := Sponsor.objects.filter_active().filter(id=sponsor_id).first()):
            raise exceptions.NotFound(detail="Sponsor not found")

        SponsorTierSponsorRelation.objects.get_or_create(tier=tier, sponsor=sponsor)
        return response.Response(data=SponsorAdminSerializer(instance=sponsor).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["delete"], url_path=f"sponsors/(?P<sponsor_id>{UUID_V4_PATTERN})")
    def remove_sponsor(self, pk: str, sponsor_id: str, *args: tuple, **kwargs: dict) -> response.Response:
        if not (relation := SponsorTierSponsorRelation.objects.filter(tier_id=pk, sponsor_id=sponsor_id).first()):
            raise exceptions.NotFound(detail="Sponsor is not associated with this tier")

        relation.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_SPONSOR]) for m in ADMIN_METHODS})
class SponsorAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SponsorAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Sponsor.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_SPONSOR],
        responses={status.HTTP_200_OK: SponsorTierAdminSerializer(many=True)},
    )
    @decorators.action(detail=True, methods=["get"], url_path="tiers")
    def list_tiers(self, *args: tuple, **kwargs: dict) -> response.Response:
        sponsor: Sponsor = self.get_object()
        tier_id_qs = SponsorTierSponsorRelation.objects.filter(sponsor=sponsor).values_list("tier_id", flat=True)
        tiers = SponsorTier.objects.filter_active().filter(id__in=tier_id_qs)
        return response.Response(data=SponsorTierAdminSerializer(instance=tiers, many=True).data)
