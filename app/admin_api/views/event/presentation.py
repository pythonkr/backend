from __future__ import annotations

from admin_api.serializers.event.presentation import (
    PresentationAdminSerializer,
    PresentationCategoryAdminSerializer,
    PresentationSpeakerAdminSerializer,
    PresentationTypeAdminSerializer,
)
from core.const.regex import UUID_V4_PATTERN
from core.const.tag import OpenAPITag
from core.permissions import IsSuperUser
from core.viewset.json_schema_viewset import JsonSchemaViewSet
from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationCategoryRelation,
    PresentationSpeaker,
    PresentationType,
)
from rest_framework import decorators, exceptions, request, response, status, viewsets

ADMIN_METHODS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationTypeAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationTypeAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = PresentationType.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION],
        responses={status.HTTP_200_OK: PresentationCategoryAdminSerializer(many=True)},
    )
    @decorators.action(detail=True, methods=["get"], url_path="categories")
    def list_categories(self, *args: tuple, **kwargs: dict) -> response.Response:
        categories = PresentationCategory.objects.filter_active().filter(type=self.get_object())
        return response.Response(data=PresentationCategoryAdminSerializer(instance=categories, many=True).data)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION],
        request=PresentationCategoryAdminSerializer,
        responses={status.HTTP_201_CREATED: PresentationCategoryAdminSerializer},
    )
    @decorators.action(detail=True, methods=["post"], url_path="categories")
    def add_category(self, request: request.Request, *args: tuple, **kwargs: dict) -> response.Response:
        serializer = PresentationCategoryAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(data=serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION],
        request=PresentationCategoryAdminSerializer,
        responses={status.HTTP_200_OK: PresentationCategoryAdminSerializer},
    )
    @decorators.action(detail=True, methods=["patch"], url_path=f"categories/(?P<category_id>{UUID_V4_PATTERN})")
    def update_category(self, request: request.Request, pk: str, category_id: str, *args, **kwargs):
        if not (category := PresentationCategory.objects.filter_active().filter(type_id=pk, id=category_id).first()):
            raise exceptions.NotFound(detail="Category not found.")

        serializer = PresentationCategoryAdminSerializer(instance=category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(data=serializer.data)

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["delete"], url_path=f"categories/(?P<category_id>{UUID_V4_PATTERN})")
    def delete_category(self, pk: str, category_id: str, *args: tuple, **kwargs: dict) -> response.Response:
        if not (category := PresentationCategory.objects.filter_active().filter(type_id=pk, id=category_id).first()):
            raise exceptions.NotFound(detail="Category not found.")

        category.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = Presentation.objects.get_all_nested_data().select_related("created_by", "updated_by", "deleted_by")

    @extend_schema(
        tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION],
        responses={status.HTTP_200_OK: PresentationCategoryAdminSerializer(many=True)},
    )
    @decorators.action(detail=True, methods=["get"], url_path="categories")
    def list_categories(self, *args: tuple, **kwargs: dict) -> response.Response:
        categories = self.get_object().active_categories
        return response.Response(data=PresentationCategoryAdminSerializer(instance=categories, many=True).data)

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION], responses={status.HTTP_201_CREATED: None})
    @decorators.action(detail=True, methods=["post"], url_path="categories/(?P<category_id>{UUID_V4_PATTERN})")
    def add_category(self, pk: str, category_id: str, *args: tuple, **kwargs: dict) -> response.Response:
        PresentationCategoryRelation.objects.get_or_create(presentation_id=pk, category_id=category_id)
        return response.Response(status=status.HTTP_201_CREATED)

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION], responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["delete"], url_path="categories/(?P<category_id>{UUID_V4_PATTERN})")
    def remove_category(self, pk: str, category_id: str, *args: tuple, **kwargs: dict) -> response.Response:
        if not (
            relation := PresentationCategoryRelation.objects.filter(presentation_id=pk, category_id=category_id).first()
        ):
            raise exceptions.NotFound(detail="Category is not associated with this presentation.")

        relation.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(**{m: extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION]) for m in ADMIN_METHODS})
class PresentationSpeakerAdminViewSet(JsonSchemaViewSet, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = PresentationSpeakerAdminSerializer
    permission_classes = [IsSuperUser]
    queryset = PresentationSpeaker.objects.filter_active().select_related("created_by", "updated_by", "deleted_by")

    def get_queryset(self) -> models.QuerySet[PresentationSpeaker]:
        return super().get_queryset().filter(presentation_id=self.kwargs["presentation_id"])
