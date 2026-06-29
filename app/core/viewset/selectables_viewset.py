from core.const.tag import OpenAPITag
from django.db.models.query import QuerySet
from drf_spectacular import openapi, types, utils
from rest_framework import decorators, response, status, viewsets


class SelectablesMixin(viewsets.GenericViewSet):
    @staticmethod
    def _get_choices_from_queryset(qs: QuerySet, is_nullable: bool) -> list[dict]:
        choices: list[dict] = [{"const": None, "title": "빈 값"}] if is_nullable else []

        if hasattr(qs, "get_choices_queryset"):
            qs = qs.get_choices_queryset()

        if hasattr(qs, "filter_active"):
            qs = qs.filter_active()
        elif hasattr(qs.model, "is_active"):
            qs = qs.filter(is_active=True)

        for row in qs:
            item: dict = {"const": str(row.pk), "title": str(row)}
            if hasattr(row, "get_choice_meta") and (meta := row.get_choice_meta()):
                item["meta"] = meta
            choices.append(item)

        return choices

    @utils.extend_schema(
        tags=[OpenAPITag.ADMIN_JSON_SCHEMA],
        summary="Selectables (this model's instances as choices)",
        responses={status.HTTP_200_OK: openapi.OpenApiResponse(response=types.OpenApiTypes.OBJECT)},
    )
    @decorators.action(detail=False, methods=["get"], url_path="selectables")
    def response_selectables(self, *args: tuple, **kwargs: dict) -> response.Response:
        qs = self.get_queryset()
        return response.Response(
            data={
                "results": self._get_choices_from_queryset(qs, False),
                "meta_schema": getattr(qs.model, "choices_meta_schema", None) or {},
            }
        )
