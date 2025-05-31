from __future__ import annotations

import typing

from admin_api.serializers.cms import PageAdminSerializer, SectionAdminSerializer, SitemapAdminSerializer
from cms.models import Page, Section, Sitemap
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_standardized_errors.openapi_serializers import (
    ValidationErrorEnum,
    ValidationErrorResponseSerializer,
    ValidationErrorSerializer,
)
from rest_framework import decorators, request, response, status, viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


class SectionData(typing.TypedDict):
    id: typing.NotRequired[str]
    page_id: typing.NotRequired[str]
    order: int
    body_ko: str
    body_en: str


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_CMS]) for m in ADMIN_METHODS})
class SitemapAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = SitemapAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Sitemap.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_CMS]) for m in ADMIN_METHODS})
class PageAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    serializer_class = PageAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Page.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")

    @staticmethod
    def _response_section_validation_error(detail: str) -> response.Response:
        return response.Response(
            data=ValidationErrorResponseSerializer(
                instance={
                    "type": ValidationErrorEnum.VALIDATION_ERROR,
                    "errors": ValidationErrorSerializer(
                        instance=[
                            {
                                "code": "section_validation_error",
                                "detail": detail,
                                "attr": "sections",
                            },
                        ],
                        many=True,
                    ).data,
                },
            ).data,
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(tags=[OpenAPITag.ADMIN_CMS], responses={status.HTTP_200_OK: SectionAdminSerializer(many=True)})
    @decorators.action(detail=True, methods=["get"], url_path="section")
    def list_sections(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not (page_id := kwargs.get("pk")):
            return self._response_section_validation_error("페이지 ID가 제공되지 않았습니다.")

        return response.Response(
            data=SectionAdminSerializer(
                instance=(
                    Section.objects.filter_active()
                    .filter(page_id=page_id)
                    .select_related("created_by", "updated_by", "deleted_by")
                    .order_by("order")
                ),
                many=True,
            ).data,
        )

    @extend_schema(
        tags=[OpenAPITag.ADMIN_CMS],
        request=SectionAdminSerializer(many=True),
        responses={
            status.HTTP_200_OK: SectionAdminSerializer(many=True),
            status.HTTP_400_BAD_REQUEST: ValidationErrorResponseSerializer,
        },
    )
    @decorators.action(detail=True, methods=["put"], url_path="section/bulk-update")
    @transaction.atomic
    def bulk_update_sections(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        if not (page_id := kwargs.get("pk")):
            return self._response_section_validation_error("페이지 ID가 제공되지 않았습니다.")

        section_qs = Section.objects.filter_active().filter(page_id=page_id).order_by("order")
        sections_data: list[SectionData] = request.data.get("sections", [])
        if not isinstance(sections_data, list):
            return self._response_section_validation_error("섹션 데이터는 리스트 형식이어야 합니다.")
        if not sections_data:
            return self._response_section_validation_error("섹션 데이터가 비어 있습니다.")

        id_in_new_sections = {sid for section_datum in sections_data if (sid := section_datum.get("id"))}
        section_qs.exclude(id__in=id_in_new_sections).delete()

        for section_datum in sections_data:
            section_id = section_datum.get("id")
            section_datum["page"] = page_id
            section_instance: Section | None = section_id and section_qs.filter(id=section_id).first()

            if section_id and not section_instance:
                return self._response_section_validation_error(f"<{section_id}> 섹션이 존재하지 않습니다.")

            serializer = SectionAdminSerializer(instance=section_instance, data=section_datum)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return response.Response(data=SectionAdminSerializer(instance=section_qs, many=True).data)
